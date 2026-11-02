# DevOps Task Manager

A small Flask task manager built for practising a Jenkins CI/CD pipeline with Docker on AWS EC2.

```
GitHub → Jenkins → Code Checkout → Docker Build → Test → Docker Run → Browser Access
```

(The Jenkinsfile runs the tests *before* building the image, so a failing test never produces a deployed container.)

## 1. Project overview

**Features:** add a task, list tasks, mark complete, delete, show creation time, show total/completed/pending counts, `/health` endpoint, responsive UI, input validation and error pages.

**Storage:** in memory only. There is no database and no Docker Compose. Tasks disappear when the container restarts, which is intentional for this exercise.

**Stack:** Python 3.12, Flask, Gunicorn, HTML/CSS, pytest, Docker, Jenkins, Git/GitHub, Ubuntu on AWS EC2.

**Routes**

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Task page |
| POST | `/tasks` | Add a task (form) |
| POST | `/tasks/<id>/complete` | Mark complete (form) |
| POST | `/tasks/<id>/delete` | Delete (form) |
| GET | `/health` | `200` + JSON status |
| GET | `/api/tasks` | List tasks as JSON |
| POST | `/api/tasks` | Create task from JSON |
| PATCH | `/api/tasks/<id>/complete` | Complete via API |
| DELETE | `/api/tasks/<id>` | Delete via API |

## 2. Architecture

```
Developer ── git push ──▶ GitHub
                            │
                     Jenkins (on EC2, agent label "raj")
                            │
   Checkout → venv + pip install → pytest → docker build → docker run → curl /health
                            │
                  Docker container (Gunicorn on 0.0.0.0:8000)
                            │
        EC2 security group (TCP 8000) ──▶ Browser: http://<EC2-PUBLIC-IP>:8000
```

Gunicorn runs **one worker with four threads**. With in-memory storage, multiple workers would each hold a different task list.

## 3. Folder structure

```
devops-task-manager/
├── app.py                 Flask app, in-memory store, routes, validation
├── requirements.txt       Runtime dependencies (Flask, Gunicorn)
├── requirements-dev.txt   Runtime + pytest (used by Jenkins and local testing)
├── pytest.ini             Test paths, adds project root to the import path
├── Dockerfile             Image definition
├── Jenkinsfile            Declarative pipeline
├── .dockerignore          Keeps tests, .git, venvs out of the image
├── .gitignore
├── README.md
├── templates/
│   ├── index.html         Main page
│   └── error.html         404/405/etc. page
├── static/
│   └── style.css
└── tests/
    └── test_app.py
```

## 4. Prerequisites

- Git and a GitHub account
- Python 3.10+ with `venv` (for local runs and for the Jenkins agent)
- Docker Engine
- Jenkins (for the CI/CD part) and `curl` on the Jenkins agent
- An AWS account (for the EC2 part)

## 5. Local setup (no Docker)

```bash
cd devops-task-manager
python3 -m venv .venv                  # create an isolated Python environment
source .venv/bin/activate              # use it (Windows: .venv\Scripts\activate)
pip install -r requirements-dev.txt    # install Flask, Gunicorn, pytest
python app.py                          # start the dev server on 0.0.0.0:8000
```

Open <http://localhost:8000>. Stop with `Ctrl+C`.

## 6. Run the tests

```bash
pytest -v        # run every test, verbose; no database or network needed
```

## 7. Docker: build and run

```bash
# Build an image named devops-task-manager with tag latest from the Dockerfile in "."
docker build -t devops-task-manager:latest .

# Run it in the background (-d), name it, publish container port 8000 on host port 8000
docker run -d \
  --name devops-task-manager \
  -p 8000:8000 \
  devops-task-manager:latest
```

Open <http://localhost:8000>.

Useful commands:

```bash
docker ps                                   # is it running? (STATUS shows "healthy" after ~10s)
docker logs -f devops-task-manager          # follow application logs (Ctrl+C to stop following)
curl http://localhost:8000/health           # should print JSON with "status": "ok"
docker stop devops-task-manager             # stop the container
docker rm devops-task-manager               # remove the stopped container
```

## 8. Upload the project to GitHub

1. Create an empty repository on GitHub (no README, no .gitignore), e.g. `devops-task-manager`.
2. Then:

```bash
cd devops-task-manager
git init                                   # start a repository
git add .                                  # stage all files (.gitignore keeps junk out)
git commit -m "Initial commit"             # save the first snapshot
git branch -M main                         # name the branch main
git remote add origin https://github.com/<your-username>/devops-task-manager.git
git push -u origin main                    # upload; use a Personal Access Token as the password
```

If the repository is private, Jenkins needs a credential for it (see section 9).

## 9. Jenkins setup and job configuration

### 9.1 Prepare the Jenkins machine

On the Ubuntu machine that runs the pipeline (the Jenkins agent; the same EC2 instance is fine):

```bash
sudo apt-get update
sudo apt-get install -y docker.io curl git python3 python3-venv python3-pip
sudo systemctl enable --now docker       # start Docker now and on every boot
sudo usermod -aG docker jenkins          # let the "jenkins" user run docker commands
sudo systemctl restart jenkins           # reload group membership
```

Install Jenkins itself by following the official Ubuntu instructions at <https://www.jenkins.io/doc/book/installing/linux/> (key and repository details change over time, so use the current page). Jenkins needs Java; the page lists supported versions.

Verify as the Jenkins user:

```bash
sudo -u jenkins docker ps       # must work without "permission denied"
sudo -u jenkins python3 -m venv /tmp/venv-check && echo venv ok
```

### 9.2 Give the agent the label `raj`

The Jenkinsfile uses `agent { label 'raj' }`. Either:

- **Manage Jenkins → Nodes → (your node, or Built-In Node) → Configure → Labels:** add `raj`, or
- Edit the `label 'raj'` line in the `Jenkinsfile` to match your node's label.

Make sure the node has at least one executor.

### 9.3 Create the pipeline job

1. **New Item** → name `devops-task-manager` → **Pipeline** → OK.
2. **Pipeline → Definition:** *Pipeline script from SCM*.
3. **SCM:** Git. **Repository URL:** your GitHub URL.
4. **Credentials:** none for a public repo. For a private repo, add a *Username with password* credential (GitHub username + Personal Access Token) under **Manage Jenkins → Credentials**, then select it here. Never put the token in the Jenkinsfile.
5. **Branch Specifier:** `*/main`. **Script Path:** `Jenkinsfile`.
6. Save.

### 9.4 Run the pipeline

Click **Build Now**. Stages:

| Stage | What it does |
|---|---|
| Code Checkout | `checkout scm` pulls the repo |
| Install Dependencies | Fresh `.venv`, installs `requirements-dev.txt` |
| Test | `pytest -v`, publishes JUnit results |
| Docker Build | Builds `devops-task-manager:latest` and `:<build number>` |
| Deploy | Removes the old container if present, starts a new one on port 8000 |
| Verify Deployment | Polls `/health` for up to ~60 s; prints container logs and fails if it never responds |

Re-running is safe: the old container is removed first, each build starts from a fresh virtualenv, and dangling image layers are pruned at the end. Optional: add a **GitHub hook trigger** or **Poll SCM** (`H/5 * * * *`) to build on every push.

## 10. AWS EC2 deployment

### 10.1 Instance configuration

| Setting | Recommendation |
|---|---|
| AMI | Ubuntu Server 24.04 LTS (or 22.04 LTS) |
| Type | `t3.small` (2 GB RAM) is comfortable if Jenkins runs on the same instance. `t3.micro`/`t2.micro` (1 GB) can work for the app alone, but Jenkins plus Docker on 1 GB is tight; add swap if you try it |
| Storage | 20 GB gp3 (the default 8 GB fills up quickly with Docker images) |
| Key pair | Create or select one to SSH in |
| Public IP | Enable auto-assign public IPv4 |

### 10.2 Security group (inbound rules)

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **My IP** | Log in to the server |
| Custom TCP | 8080 | **My IP** | Jenkins web UI (default port) |
| Custom TCP | **8000** | **My IP** (or `0.0.0.0/0` for open practice) | The application |

Port 8000 is **not** reachable from the internet until the security group allows it. In the console: **EC2 → Instances → your instance → Security → Security groups → Edit inbound rules → Add rule**. Using "My IP" is safer than `0.0.0.0/0`; your IP changes if your ISP changes it, so update the rule if the page stops loading.

### 10.3 Find the public IPv4 address

- Console: **EC2 → Instances →** select the instance → **Public IPv4 address**.
- From inside the instance (IMDSv2):

```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4
```

A stopped and restarted instance gets a new public IP unless you attach an Elastic IP.

### 10.4 Open the app

```
http://<EC2-PUBLIC-IPV4>:8000
http://<EC2-PUBLIC-IPV4>:8000/health
```

Use `http://`, not `https://`; there is no TLS in this exercise.

### 10.5 Check status and logs (on the instance)

```bash
docker ps                                  # container running? port mapping 0.0.0.0:8000->8000/tcp
docker ps -a --filter name=devops-task-manager   # includes stopped/crashed containers
docker logs --tail 100 devops-task-manager # last 100 log lines
docker logs -f devops-task-manager         # follow live
docker inspect --format '{{.State.Health.Status}}' devops-task-manager   # healthy / unhealthy
curl -i http://localhost:8000/health       # test from the instance itself
```

## 11. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Browser times out on `:8000` | Security group lacks an inbound rule for TCP 8000 from your IP, or you are using the wrong/old public IP |
| `curl localhost:8000/health` works on EC2 but not from your PC | Same as above: security group |
| `permission denied ... /var/run/docker.sock` in Jenkins | `sudo usermod -aG docker jenkins && sudo systemctl restart jenkins` |
| `python3 -m venv` fails: *ensurepip is not available* | `sudo apt-get install -y python3-venv` |
| Pipeline waits forever: *no agent with label raj* | Add label `raj` to a node or change the label in the Jenkinsfile |
| `curl: command not found` in Verify stage | `sudo apt-get install -y curl` on the agent |
| `port is already allocated` on Deploy | Something else uses 8000: `sudo ss -ltnp \| grep 8000`; stop it, or a differently named container is holding it: `docker ps` |
| Verify stage fails but the app works in a browser | Jenkins agent runs inside a container, so `localhost` is not the host. Use a host-side agent, or change the curl URL |
| `no space left on device` | `docker system df`, then `docker image prune -a` (see cleanup) |
| Tasks vanished | Expected: in-memory storage resets on every redeploy/restart |
| Jenkins is slow or killed on a small instance | Not enough RAM; use `t3.small` or larger, or add swap |
| `git push` rejected / asks for password | GitHub requires a Personal Access Token instead of a password |

## 12. Cleanup commands

```bash
docker rm -f devops-task-manager              # stop and remove the app container
docker rmi devops-task-manager:latest         # remove the image (also remove numbered tags if you want)
docker images devops-task-manager             # list all tags of the image
docker image prune -f                         # remove dangling (untagged) layers
docker system prune -f                        # remove stopped containers, unused networks, dangling images
rm -rf .venv                                  # remove the local virtualenv
```

AWS: **stop** the instance to pause compute charges (storage is still billed); **terminate** it and delete unused Elastic IPs and volumes when you are done to avoid charges.

## 13. Important implementation decisions

- **Single Gunicorn worker + threads**: keeps one shared in-memory task list.
- **Application factory (`create_app`)**: each test gets a fresh, empty store; Gunicorn uses the module-level `app`.
- **Thread lock around the store**: safe under Gunicorn threads.
- **Non-root container user** and a minimal `COPY` list (only app code, templates, static files).
- **Python-based HEALTHCHECK** because `python:slim` has no `curl`.
- **`requirements-dev.txt`** keeps pytest out of the production image while Jenkins still installs it.
- **Tests run in a virtualenv on the agent before the image is built**, so broken code is never deployed. The agent needs `python3-venv`.
- **No registry or credentials**: the image stays on the local Docker host.
- **`--restart unless-stopped`** brings the container back after an instance reboot.
- **Validation**: titles required (max 100 chars), details max 300; Jinja auto-escaping prevents HTML injection.
- **No CSRF protection**: acceptable for a practice app with no login and no persistent data; add Flask-WTF before using it for anything real.
