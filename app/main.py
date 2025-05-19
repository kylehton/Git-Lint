from fastapi import FastAPI, Request, BackgroundTasks
from openai import OpenAI
import os
import dotenv
import httpx
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

openAIClient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
githubKey = os.getenv("GITHUB_ACCESS_TOKEN")

systemPrompt = """
    The input is the raw diff of a pull request. You are a meticulous code reviewer with deep expertise in algorithms, 
    data structures, and software engineering best practices.
    Your job:
    Identify every single change, no matter how small (e.g., comment removal, spacing, refactoring).
    Some lines are going to be low impact changes, such as spacing, formatting, comment removal, etc.
    These should NOT be analyzed heavily, and only briefly mentioned at the bottom of the review, before the summary.
    For each impactful changed line, analyze and explain, consolidating analysis where you can, and only mentioning the most impactful changes:
    What was changed.
    Why it was changed (or likely changed).
    Whether the change improves or worsens the code.
    If further improvements or abstractions can be made (e.g., avoid repetition, wasted memory, lack of modularity).
    If no code change is necessary, but improvements are possible (e.g., abstraction opportunities), suggest those.
    Return only the changed lines with explanations — no restating of diffs or unchanged code.
    Do not return code in diff format. Use a human-readable explanation paired directly with the changed lines.
    Your review should help turn the code into the most scalable, efficient, and readable version possible. Assume the 
    author wants direct, precise, and actionable feedback with no fluff. Do not summarize at the start — only provide a 
    detailed final summary at the end of the changes.
    """

app = FastAPI()

# Store background tasks to prevent garbage collection
background_tasks_set = set()

async def review_diff(diff: str):
    try:
        response = openAIClient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": diff}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error occurred during processing of message: {e}")
        return {"error": str(e)}
    

async def post_comment(issue_url: str, comment: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(issue_url+"/comments", json={"body": comment}, 
            headers={
                "Authorization": f"Bearer {githubKey}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        if response.status_code == 200:
            return {"message": "Comment posted successfully"}
        else:
            return {"message": "Failed to post comment"}

async def get_diff(url: str):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        # Code 200 -> Success, 302 -> Redirect
        if response.status_code == 200 or response.status_code == 302:
            return response.text
        else:
            return {"error": "Failed to get pull request diff"}

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
    
    # Wait for all background tasks to complete
    if background_tasks_set:
        logger.info(f"Waiting for {len(background_tasks_set)} background tasks to complete")
        print(f"Waiting for {len(background_tasks_set)} background tasks to complete")
        await asyncio.gather(*background_tasks_set, return_exceptions=True)

@app.get("/")
def read_root():
    logger.info("Service is running successfully through EC2.")
    return {"Status": "200 OK"}

# Process function for review endpoint
async def process_review(diff_url: str, issue_url: str):
    try:
        logger.info("[PROCESS]: Retrieving diff from redirect URL")
        diff = await get_diff(diff_url)
        if isinstance(diff, dict) and diff.get("error"):
            logger.error(f"Error getting diff: {diff['error']}")
            return

        logger.info("[PROCESS]: Reviewing diff and creating comment")
        review = await review_diff(diff)
        if isinstance(review, dict) and review.get("error"):
            logger.error(f"Error reviewing diff: {review['error']}")
            return

        logger.info("[PROCESS]: Posting comment")
        response = await post_comment(issue_url, review)
        logger.info(f"Comment response: {response}")
    except Exception as e:
        logger.error(f"[ERROR]: {e}")
    
@app.post("/review")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    logger.info("[/review] Request received")
    
    data = await request.json()
    diff_url = data["pull_request"]["diff_url"]
    issue_url = data["pull_request"]["issue_url"]
    
    background_tasks.add_task(process_review, diff_url, issue_url)
    
    '''
    task = asyncio.create_task(process_review(diff_url, issue_url))
    background_tasks_set.add(task)
    task.add_done_callback(lambda t: background_tasks_set.remove(t))
    '''
    logger.info("[/review] Responding immediately")
    
    return {"message": "Review started, response will be posted shortly."}