from logic_functions.s3_upload import download_chunk_store_from_s3, load_chunk_store, get_full_chunk_by_id, save_chunk_store_locally, upload_chunk_store_to_s3
from logic_functions.embeddings import upsert_to_pinecone, hash_content

from pinecone import Pinecone
from openai import OpenAI
import os
import dotenv
import httpx
import logging
import re
import boto3
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

openAIClient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
githubKey = os.getenv("GITHUB_ACCESS_TOKEN")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_OBJECT_KEY = "chunk_s3.json"
s3 = boto3.client("s3")

index = pc.Index("git-lint")

# Global variable to store the chunk store
chunk_store = None


##### FUNCTIONS (are written in order they are called in function pipeline) #####

### CALLED BY: run_orchestration_agent
### PURPOSE: Gets S3 chunks of codebase to be used, which sets the global variable correctly
def initialize_chunk_store():
    """Initializes the global chunk_store by downloading it from S3."""
    global chunk_store
    print("[PROCESS]: Downloading chunk store from S3")
    store_path = download_chunk_store_from_s3()
    chunk_store = load_chunk_store(store_path)
    print("[PROCESS]: Chunk store initialized")

### CALLED BY: run_orchestration_agent
### PURPOSE: Retrieves the diff from the redirect URL to be used as the input for the review
# 1. Retrieve the diff from the redirect URL
# 2. Return the diff in text/string format
# @param url: str - The URL of the diff
# @return: str - The diff as text
async def get_diff(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        # Code 200 -> Success, 302 -> Redirect
        if response.status_code == 200 or response.status_code == 302:
            print(f"Diff retrieved successfully: {response.text[:50]}...")
            return response.text
        else:
            return {"error": "Failed to get pull request diff"}
    

### CALLED BY: review_agent
### PURPOSE: Retrieves the context from the diff by searching the vector database for the most relevant chunks
# 1. Retrieve the file paths from the diff
# 2. Embed sizable chunks of the diff from chunk_diff()
# 3. Query the vector database for the most relevant chunks to the diff
# 4. Concatenate the most relevant chunks and return them
# @param repo_name: str - The name of the repository to be searched for context
# @param diff: str - The diff of the pull request
# @param top_k: int - The number of chunks to concatenate and return
# @return: str - concatenated string of context from the codebase
async def retrieve_context_from_diff(repo_name: str, diff: str, top_k: int = 2) -> str:
    try:
        global chunk_store
        # 1. Retrieve the file paths from the diff
        file_paths = extract_file_paths_from_diff(diff)

        # 2. Embed sizable chunks of the diff from chunk_diff()
        chunks = chunk_diff(diff)
        all_matches = []

        # 3. Embed each chunk and query the vector database for the most relevant chunks to the diff
        for chunk in chunks:
            response = openAIClient.embeddings.create(
                input=chunk,
                model="text-embedding-3-small"
            )
            vector = response.data[0].embedding

            result = index.query(
                vector=vector,
                top_k=top_k,
                include_metadata=True,
                filter={"repo": {"$eq": repo_name},
                        "path": {"$in": list(file_paths)}}  
            )

            # 4. Append the most relevant chunks to the list
            for match in result.get("matches", []):
                chunk_id = match["id"]
                full_chunk = get_full_chunk_by_id(chunk_id, chunk_store)

                if full_chunk:
                    # Log the location of the context match
                    print(f"✅ Context match from {match['metadata']['path']} (chunk {match['metadata']['chunk_id']})")
                    all_matches.append(full_chunk)
                else:
                    logger.warning(f"⚠️ Chunk ID {chunk_id} not found in chunk store")

        return "\n\n".join(all_matches)
    
    except Exception as e:
        print(f"Error occurred during retrieval of context from diff: {e}")
        return {"error": str(e)}


### CALLED BY: retrieve_context_from_diff
### PURPOSE: Extracts the file paths from the diff to be used as a filter for the context search
# 1. Extract the file paths from the diff
# 2. Append the file paths into a set, and return the set
# @param diff: str - The diff of the pull request
# @return: set[str] - The file paths from the diff
def extract_file_paths_from_diff(diff: str) -> list[str]:
    paths = set()

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            match = re.search(r"diff --git a/(.*?) b/(.*)", line)
            if match:
                paths.add(match.group(2))  # destination path
        elif line.startswith("+++ b/"):
            paths.add(line.replace("+++ b/", "").strip())
    
    return list(paths)

# Function to split file for parallel processing reviews
def split_diff_by_file(diff_text: str) -> dict[str, str]:
    """
    Splits a diff string into a dictionary where keys are file paths
    and values are the diff content for each file.
    """
    files_diff = {}
    # Split the diff by the file delimiter 'diff --git'
    diff_parts = diff_text.split('diff --git ')[1:]
    
    for part in diff_parts:
        # The first line contains the file paths
        lines = part.split('\n')
        header_line = lines[0]
        
        # Extract the 'b' path as the identifier
        try:
            file_path = header_line.split(' b/')[1].strip()
        except IndexError:
            # Handle cases where the split doesn't work as expected
            continue
            
        # Reconstruct the diff for this file
        file_diff_content = 'diff --git ' + part
        files_diff[file_path] = file_diff_content
        
    return files_diff


### CALLED BY: retrieve_context_from_diff
### PURPOSE: Splits the entire diff into chunks, which, if longer than min_len, are added to the vector database
# 1. Chunk the diff
# 2. Measure the length of each chunk to check usefulness as an embedding
# 3. Append the chunks into a list, and return the list
# @param diff: str - The diff of the pull request
# @param min_len: int - The minimum length of a chunk
# @return: list[str] - The chunks of the diff
def chunk_diff(diff: str, min_len: int = 50) -> list[str]:

    chunks = []
    raw_chunks = re.split(r"^diff --git.+?^(@@.+?@@)", diff, flags=re.MULTILINE | re.DOTALL)

    for chunk in raw_chunks:
        cleaned = chunk.strip()
        if len(cleaned) >= min_len:
            chunks.append(cleaned)
    return chunks


### CALLED BY: run_orchestration_agent
### PURPOSE: Posts the comment to the issue
# 1. Post the comment to the issue
# 2. Return a success message
# @param issue_url: str - The URL of the issue
# @param comment: str - The comment to be posted
# @return: dict - The response from the API
async def post_comment(issue_url: str, comment: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(issue_url+"/comments", json={"body": comment}, 
            headers={
                "Authorization": f"Bearer {githubKey}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        if response.status_code == 200 or response.status_code == 201:
            return {"message": "Comment posted successfully"}
        else:
            return {"message": "Failed to post comment"}

async def get_file_content(repo_name: str, file_path: str) -> str:
    try:
        url = f"https://raw.githubusercontent.com/kylehton/{repo_name}/main/{file_path}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Failed to get file from {url}: {response.status_code}")
                return None
    except Exception as e:
        print(f"Error getting file content: {e}")
        return None

async def update_file_embeddings(repo_name: str, diff: str):
    global chunk_store

    try:
        # Get modified file paths from diff
        file_paths = extract_file_paths_from_diff(diff)
        if not file_paths:
            print("No files to update")
            return

        # Track all embedded chunks for saving
        all_embedded_chunks = []

        # Process each modified file
        for file_path in file_paths:
            # Get file content from GitHub
            content = await get_file_content(repo_name, file_path)
            if not content:
                logger.warning(f"Could not get content for {file_path}")
                continue

            # Find and delete existing chunks for this file
            chunks_to_delete = [chunk_id for chunk_id, chunk_data in chunk_store.items() if chunk_data.get("path") == file_path]
            if chunks_to_delete:
                try:
                    # Delete from Pinecone
                    index.delete(ids=chunks_to_delete)
                    print(f"Deleted {len(chunks_to_delete)} chunks from Pinecone for {file_path}: {chunks_to_delete}")
                    # Remove from local chunk store
                    for chunk_id in chunks_to_delete:
                        chunk_store.pop(chunk_id, None)
                    print(f"Deleted {len(chunks_to_delete)} chunks from chunk_store for {file_path}")
                except Exception as e:
                    print(f"Error deleting chunks for {file_path}: {e}")

            # Create new chunks from file content
            chunks = []
            patterns = {
                ".py": r"(?=def |class )",
                ".js": r"(?=function |class |const |let |var )",
                ".java": r"(?=public |private |protected |class )",
            }
            ext = os.path.splitext(file_path)[1]
            if ext in patterns:
                split_chunks = re.split(patterns[ext], content)
                for i, chunk in enumerate(split_chunks):
                    cleaned = chunk.strip()
                    if len(cleaned) > 50:
                        content_hash = hash_content(cleaned)
                        chunk_id = f"{file_path}-{i}-{content_hash}"
                        chunks.append({
                            "id": chunk_id,
                            "text": cleaned,
                            "metadata": {
                                "path": file_path,
                                "chunk_id": i,
                                "hash": content_hash,
                                "repo": repo_name,
                                "preview": cleaned[:200]
                            }
                        })

            if not chunks:
                logger.warning(f"No chunks created for {file_path}")
                continue

            # Embed and upsert new chunks
            embedded_chunks = []
            for chunk in chunks:
                try:
                    response = openAIClient.embeddings.create(
                        input=chunk["text"],
                        model="text-embedding-3-small"
                    )
                    chunk["embedding"] = response.data[0].embedding
                    embedded_chunks.append(chunk)
                    print(f"Embedded: {chunk['metadata']['path']} [chunk {chunk['metadata']['chunk_id']}]")
                except Exception as e:
                    print(f"Error embedding chunk {chunk['id']}: {e}")
                    continue

            if not embedded_chunks:
                logger.warning(f"No chunks were successfully embedded for {file_path}")
                continue

            # Upsert to Pinecone
            try:
                upsert_to_pinecone(embedded_chunks, index)
                print(f"Upserted {len(embedded_chunks)} chunks to Pinecone for {file_path}")
            except Exception as e:
                print(f"Error upserting to Pinecone: {e}")
                continue

            # Add to local chunk store
            for chunk in embedded_chunks:
                try:
                    chunk_store[chunk["id"]] = {
                        "text": chunk["text"],
                        "path": chunk["metadata"]["path"],
                        "chunk_id": chunk["metadata"]["chunk_id"]
                    }
                except Exception as e:
                    print(f"Error updating store for chunk {chunk['id']}: {e}")
                    continue

            all_embedded_chunks.extend(embedded_chunks)

        # Save updated store and upload to S3
        try:
            # Save the entire chunk_store to S3
            with open("/tmp/chunk_s3.json", "w") as f:
                json.dump(chunk_store, f, indent=2)
            upload_chunk_store_to_s3()
            print(f"Successfully updated embeddings for {len(file_paths)} files")
        except Exception as e:
            print(f"Error saving store: {e}")
            raise

    except Exception as e:
        print(f"Error updating file embeddings: {e}")
        raise