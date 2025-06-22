# GitLint

An AI-powered code review agentic system that automatically analyzes pull requests using OpenAI and posts review comments and suggestions back to the pull request.

---

## Overview

**GitLint** is a FastAPI-based microservice deployed on AWS Lambda that:
- Receives GitHub webhook events for pull requests
- Extracts code diffs from the PR
- Uses OpenAI's language models to analyze the changes
- Suggests improvements, flags issues, and identifies errors
- Posts comments or reviews directly to the pull request
- Utilizes a RAG system to contextualize analysis
- Automated code review, commenting, and updates of repository embeddings

The overall process is managed through an orchestration agent and a reviewing agent, which run reviews per file in parallel,
being mindful of possible token context limits.
---

## Tech Stack

- **Python 3.13**
- **FastAPI**
- **Docker**
- **OpenAI Agents API**
- **GitHub Webhooks & GitHub REST API**
- **AWS Lambda & S3**
- **PineconeDB**

---

