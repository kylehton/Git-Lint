from app.agent_workflow.run_agent import run_orchestration_agent
from fastapi import FastAPI, Request, BackgroundTasks
from mangum import Mangum
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

background_tasks_set = set()

app = FastAPI()

@app.get("/")
def read_root():
    logger.info("Service is running successfully through EC2 instance of Docker container.")
    return {"Status": "200 OK"}
    
@app.post("/review")
async def webhook(request: Request, background_tasks: BackgroundTasks): 
    print("[/review] Request received")

    # Handle ping event from GitHub Webhook
    if request.headers.get("X-GitHub-Event") == "ping":
        logger.info("[/review] Ping received")
        return {"message": "Ping received!"}
    elif request.headers.get("X-GitHub-Event") == "pull_request":
        data = await request.json()
        if data["action"] != "opened":
            logger.info("[/review] Pull request merged, skipping review")
            return {"message": "Pull request merged, skipping review"}
        full_repo = data["repository"]["full_name"]
        repo_name = full_repo.split("/")[-1] # Parse repo name for custom filter search
        diff_url = data["pull_request"]["diff_url"]
        issue_url = data["pull_request"]["issue_url"]
        
        # Call function chain to process diff and generate a review comment
        background_tasks.add_task(run_orchestration_agent, diff_url, repo_name, issue_url)
        print("[/review] Responding immediately")
        
        # Return response to GitHub to confirm receiving Pull Request webhook
        return {"message": "Review started, response will be posted shortly."}
    else:
        # Return error message if event is not a ping or pull request
        logger.info("[/review] Unknown event received")
        return {"message": "Unknown event received"}
    
handler = Mangum(app)