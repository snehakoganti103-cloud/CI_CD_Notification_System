BUILDWATCH - CI/CD BUILD FAILURE NOTIFICATION SYSTEM

1. Install Python 3.10 or newer.
2. Open a terminal inside this project folder.
3. Create and activate a virtual environment:
   Windows: py -m venv venv
   Windows: venv\Scripts\activate
   macOS/Linux: python3 -m venv venv
   macOS/Linux: source venv/bin/activate
4. Install packages:
   pip install -r requirements.txt
5. Set a secret token and Flask secret key.

   Windows PowerShell:
   $env:CI_NOTIFICATION_TOKEN="use-a-long-random-token"
   $env:FLASK_SECRET_KEY="use-another-long-random-secret"

   macOS/Linux:
   export CI_NOTIFICATION_TOKEN="use-a-long-random-token"
   export FLASK_SECRET_KEY="use-another-long-random-secret"

6. Start the website:
   python app.py
7. Open http://127.0.0.1:5000 and register an account.
8. Add a repository using owner/repository format.
9. In the GitHub repository, open Settings > Secrets and variables > Actions.
   Add CI_NOTIFICATION_URL with your deployed app URL plus /api/builds.
   Add CI_NOTIFICATION_TOKEN with the same token used by the Flask server.
10. Copy .github/workflows/ci.yml into the monitored GitHub repository at
    .github/workflows/ci.yml, then commit and push it.

IMPORTANT:
- GitHub Actions runners cannot send requests to your computer's localhost.
  Deploy this Flask app to a publicly reachable HTTPS server before using
  GitHub-hosted runners, or use a secure tunnel for development.
- Keep CI_NOTIFICATION_TOKEN and FLASK_SECRET_KEY private.
- Use HTTPS in production. Set debug=False in production.
- This starter project stores build status and links to GitHub logs. It does
  not retrieve raw GitHub job logs or send email notifications.
- The database is created automatically the first time app.py is run.
