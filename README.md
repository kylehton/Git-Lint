# GitLint

An AI-powered code review bot that automatically analyzes pull requests using OpenAI and posts review comments and suggestions back to the pull request.

---

## Overview

**GitLint** is a FastAPI-based microservice deployed on AWS EC2 that:
- Receives GitHub webhook events for pull requests
- Extracts code diffs from the PR
- Uses OpenAI's language models to analyze the changes
- Suggests improvements, flags issues, and identifies errors
- Posts comments or reviews directly to the pull request

---

## Tech Stack

- **Python 3.13**
- **FastAPI**
- **Docker & Docker Compose**
- **OpenAI API**
- **GitHub Webhooks & REST API**
- **AWS EC2**

---

