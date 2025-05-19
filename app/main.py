from fastapi import FastAPI, Request
from openai import OpenAI
from pydantic import BaseModel
import os
import dotenv
import httpx

dotenv.load_dotenv()

openAIClient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
githubKey = os.getenv("GITHUB_TOKEN")

systemPrompt = """
    The input is the raw diff of a pull request. You are a meticulous code reviewer with deep expertise in algorithms, 
    data structures, and software engineering best practices.
    Your job:
    Identify every single change, no matter how small (e.g., comment removal, spacing, refactoring).
    For each changed line, analyze and explain:
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
        print(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error occurred during processing of message: {e}")
        return {"error": str(e)}
    
def comment_review(review: str):
    # TODO: Comment the review onto the pull request
    pass

async def get_diff(url: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return {"error": "Failed to get pull request diff"}

    
@app.post("/review")
async def webhook(request: Request):
    data = await request.json()
    print(data["pull_request"]["diff_url"])
    diff = await get_diff(data["pull_request"]["diff_url"])
    if isinstance(diff, dict) and diff.get("error"):
        return {"message": "Error in getting the diff"}
    review = await review_diff(diff)
    if isinstance(review, dict) and review.get("error"):
        return {"message": "Error in reviewing the diff"}

    return {"message": "Diff reviewed successfully", "review": review}

