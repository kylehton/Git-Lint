from agents import Agent, Runner
from dotenv import load_dotenv
import asyncio

from logic_functions.diff_functions import get_diff, split_diff_by_file, retrieve_context_from_diff, post_comment, update_file_embeddings, initialize_chunk_store
from app.agent_workflow.review_agent import run_review_agent

load_dotenv()

summarizer_agent = Agent(
    name="Summarizer Agent",
    instructions="You have been provided with a list of reviews for a pull request, with each review corresponding to a single file. Your task is to synthesize these individual reviews into a single, cohesive pull request comment. Make sure to format it nicely in markdown.",
    model='gpt-4o'
)

async def run_orchestration_agent(url: str, repo_name: str, issue_url: str):
    # 0. Initialize the chunk store
    initialize_chunk_store()

    # 1. Get the full diff
    diff = await get_diff(url)
    if isinstance(diff, dict) and diff.get("error"):
        print(f"Error getting diff: {diff['error']}")
        return

    # 2. Split the diff by file
    file_diffs = split_diff_by_file(diff)

    # 3. Create review tasks for each file
    review_tasks = []
    for file_path, file_diff in file_diffs.items():
        # For each file, retrieve context and then run the review agent
        async def review_task(path=file_path, diff_content=file_diff):
            context = await retrieve_context_from_diff(repo_name, diff_content)
            review = await run_review_agent(path, diff_content, context)
            return f"### Review for `{path}`:\n\n{review}"
        
        review_tasks.append(review_task())

    # 4. Run review tasks in parallel
    individual_reviews = await asyncio.gather(*review_tasks)

    # 5. Aggregate and summarize the reviews
    full_review_text = "\n\n".join(individual_reviews)
    
    final_prompt = f"Here are the reviews for each file in the pull request:\n\n{full_review_text}\n\nPlease synthesize this into a single, cohesive pull request comment."
    
    final_review = await Runner.run(summarizer_agent, final_prompt)

    # 6. Post the final review to the issue URL
    await post_comment(issue_url, final_review.final_output)

    # 7. Update embeddings for the files in the diff
    await update_file_embeddings(repo_name, diff)

    return final_review.final_output

    
