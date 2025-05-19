from fastapi import FastAPI, Request
from openai import OpenAI
import os
import dotenv
import httpx
import asyncio

dotenv.load_dotenv()

openAIClient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
githubKey = os.getenv("GITHUB_TOKEN")

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

systemPrompt = """
    The input is the raw diff of a pull request. You are a meticulous code reviewer with deep expertise in algorithms, 
    data structures, and software engineering best practices.
    Your job:
    Identify every single change, no matter how small (e.g., comment removal, spacing, refactoring).
    For each changed line, analyze and explain:
    What was changed,
    Why it was changed (or likely changed).
    Whether the change improves or worsens the code.
    If further improvements or abstractions can be made (e.g., avoid repetition, wasted memory, lack of modularity).
    If no code change is necessary, but improvements are possible (e.g., abstraction opportunities), suggest those.
    Return only the changed lines with explanations — no restating of diffs or unchanged code.
    Do not return code in diff format. Use a human-readable explanation paired directly with the changed lines.
    Your review should help turn the code into the most scalable, efficient, and readable version possible. Assume the author 
    wants direct, precise, and actionable feedback with no fluff. Do not summarize at the start — only provide a detailed 
    final summary at the end of the changes.
    """

@app.get("/")
def read_root():
    print("Service is running successfully through EC2.")
    return {"Status": "200 OK"}


async def review_diff(diff: str):
    try:
        response = openAIClient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": diff}
            ]
        )
        print("Input: ", diff)
        print("Response: ", response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error occurred during processing of message: {e}")
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
            print("URL Contents: ", response.text)
            return response.text
        else:
            return {"error": "Failed to get pull request diff"}

@app.post("/test")
async def webhook(request: Request):
    async def process():
        print("✅ Background task running!")

    asyncio.create_task(process())
    return {"message": "started"}
    
@app.post("/review")
async def webhook(request: Request):
    data = await request.json()
    diff_url = data["pull_request"]["diff_url"]
    issue_url = data["pull_request"]["issue_url"]

    async def process():
        try:
            print("[PROCESS]: Retrieving diff from redirect URL")
            diff = await get_diff(diff_url)
            if isinstance(diff, dict) and diff.get("error"):
                print("Error getting diff:", diff["error"])
                return

            print("[PROCESS]: Reviewing diff and creating comment")
            review = await review_diff(diff)
            if isinstance(review, dict) and review.get("error"):
                print("Error reviewing diff:", review["error"])
                return

            print("[PROCESS]: Posting comment")
            response = await post_comment(issue_url, review)
            print("Comment response:", response)
        except Exception as e:
            print("[ERROR]:", e)

    # Call the background task
    asyncio.create_task(process())

    # Respond to GitHub immediately
    return {"message": "Review started, response will be posted shortly."}