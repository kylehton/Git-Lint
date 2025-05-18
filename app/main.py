from fastapi import FastAPI, Request
from openai import OpenAI
from pydantic import BaseModel
import os
import dotenv
import httpx

dotenv.load_dotenv()

openAIClient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
githubKey = os.getenv("GITHUB_TOKEN")

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

class PullRequestCode(BaseModel):
    diff: str

async def review_code_diff(pullRequest: PullRequestCode):
    try:
        response = openAIClient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "The input are the changes of a pull request. You are a helpful assistant with a deep understanding of algorithms and data structures. You need to review the changes for mistakes and places of improvement. Areas of Focus: Inefficient algorithms, wasted memory/space, lack of abstraction. The end result should be the most syntactically correct, cleanly factored and scalable code. At the end, give a summary of anything you have changed. For all changes, double check your work to make sure nothing is suggested is incorrect."},
                {"role": "user", "content": pullRequest.diff}
            ]
        )
        print(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error occurred during processing of message: {e}")
        return {"error": str(e)}

async def fetch_changes(endpoint: str):
    headers = {
        "Authorization": f"Bearer {githubKey}",
        "Accept": "application/vnd.github.v3+json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.github.com/repos/kylehton/kylehton/pulls/{endpoint}", headers=headers)
        return response.json()
    
    
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print(data)
    return {"message": "Webhook received"}

@app.post("/review")
def review_code_diff_endpoint(pullRequest: PullRequestCode):
    # TODO: Get the diff from the pull request
    # TODO: Review the diff (using review_code_diff() function)
    # TODO: Return the review
    return