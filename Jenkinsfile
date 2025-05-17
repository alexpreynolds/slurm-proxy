import hudson.model.Result

def remote = [:]
remote.name = "Staging APIs"
remote.host = "slurm-proxy-staging.altius.org"
remote.allowAnyHosts = true

node {
    def app

    try {

      stage('Clone Repository') {
          checkout scm
      }

      stage('Pre-Build Setup') {
        sh 'ln -sf docker/Dockerfile ./Dockerfile'
      }

      stage('Build Image') {
        app = docker.build("altiusinstitute/slurm-proxy", "--build-arg BUILD_NUMBER=${env.BUILD_NUMBER} --no-cache .")
      }

      stage('Test') {
        sh 'pytest -s --disable-warnings --tb=short tests/test_app_logging.py'
        sh 'pytest -s --disable-warnings --tb=short tests/test_task_submission_rest.py'
      }

      stage('Push Image') {
        docker.withRegistry('https://registry.hub.docker.com', 'docker-hub-credentials') {
        app.push("${env.BUILD_NUMBER}")
        app.push("latest")
        }
      }

    notifySuccess()
    }
    catch (e) {
        println(e.toString());
        println(e.getMessage());
        println(e.getStackTrace());
        notifyFail()
        currentBuild.rawBuild.@result = hudson.model.Result.FAILURE
    }
}

import groovy.transform.Field

@Field final String SUCCESS = 'SUCCESS'
@Field final String FAIL = 'FAIL'

def notifySuccess(String status = SUCCESS) {
    slackNotification(SUCCESS)
}

def notifyFail() {
    slackNotification(FAIL)
}

def slackNotification(String status = FAIL) {
    def color = '#FF0000'
    def message = "BUILD ${status}: '${env.JOB_NAME} [${env.BUILD_NUMBER}]'"

    if (status == SUCCESS) {
        color = '#00FF00'
    }
    slackSend(color: color, message: message)
}
