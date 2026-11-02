pipeline {
    // Change 'raj' to the label of your Jenkins node (agent).
    agent { label 'raj' }

    options {
        disableConcurrentBuilds()
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        APP_NAME   = 'devops-task-manager'
        IMAGE_NAME = 'devops-task-manager'
        HOST_PORT  = '8000'
    }

    stages {
        stage('Code Checkout') {
            steps {
                checkout scm
                sh 'ls -la'
            }
        }

        stage('Install Dependencies') {
            steps {
                // A fresh virtualenv per build keeps the agent clean and repeatable.
                sh '''
                    python3 --version
                    rm -rf .venv
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    . .venv/bin/activate
                    pytest -v --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    docker build -t "${IMAGE_NAME}:latest" -t "${IMAGE_NAME}:${BUILD_NUMBER}" .
                '''
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    # Remove the previous container if present (ignore "not found").
                    docker rm -f "${APP_NAME}" >/dev/null 2>&1 || true

                    docker run -d \
                        --name "${APP_NAME}" \
                        --restart unless-stopped \
                        -p "${HOST_PORT}:8000" \
                        "${IMAGE_NAME}:latest"
                '''
            }
        }

        stage('Verify Deployment') {
            steps {
                sh '''
                    for i in $(seq 1 20); do
                        if curl -fsS "http://localhost:${HOST_PORT}/health"; then
                            echo
                            echo "Deployment is healthy."
                            exit 0
                        fi
                        echo "Waiting for app (attempt $i/20)..."
                        sleep 3
                    done

                    echo "Health check failed. Last container logs:"
                    docker logs --tail 50 "${APP_NAME}" || true
                    exit 1
                '''
            }
        }
    }

    post {
        success {
            echo "Done. Open http://<EC2-PUBLIC-IP>:${HOST_PORT}"
        }
        failure {
            echo 'Pipeline failed. Check the stage logs above.'
        }
        always {
            // Remove dangling image layers left by repeated builds.
            sh 'docker image prune -f || true'
        }
    }
}
