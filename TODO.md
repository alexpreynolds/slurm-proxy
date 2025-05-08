# slurm-proxy

### In Progress

- [ ] Task submission #feat @alexpreynolds
  - [x] Replace SSH-based job submission process with RESTful call that targets specified end user and new cluster partition
    - [x] Preliminary job to create destination folders for output and error logs, before firing primary task
    - [x] Main job fired off after preliminary prep job is completed (use `job_id` as dependency)
  - [ ] Run basic test with different users
    - [x] Test overall task submission against `areynolds`
    - [ ] Test overall task submission against another user account that can access the cluster
      - [ ] Get `slurmapitest` account set up
      - [ ] Request the account is closed, if tests pass

- [x] Task SLURM REST endpoints @alexpreynolds
  - [x] Test `slurm/jobs/` and `slurmdb/job/<job_id>/` endpoints
    - [x] Ask Matt to resolve issue with `slurmdb/job/<job_id>/`
  - [x] Modify `slurm/jobs/` endpoint to return all jobs metadata associated with specified end user and newer than update_time

- [x] Task monitoring #feat @alexpreynolds
  - [x] Modify `get_current_slurm_job_metadata_by_slurm_job_id` and similar fns to support RESTful calls in addition to SSH calls
  - [x] Test RESTful monitoring (submit job, query endpoints before and after state change)

- [x] Refactor SSH and MongoDB connection code
  - [x] Move SSH and MongoDB connection code out of constants/helpers and into seperate singleton classes
  - [x] Modify `task_*` calls to SSH and MongoDB to use singleton connection

- [ ] General
  - [ ] Replace remaining print statements with logger calls and set level (DEBUG)
  - [ ] Allow the task payload to pass in `name`, `cmd`, and `default_params` properties without need to customize `constants.py`

- [ ] MongoDB database backup strategy
  - [ ] Definition
  - [ ] Implementation as part of Docker distribution
  - [ ] Test how app behaves if mongodb service is brought down
    - [ ] Decide how to report errors

- [ ] Docker deployment #feat @alexpreynolds
  - [x] Modify Dockerfile and test w/o environment variables 2025-04-29
  - [x] Meet with Mike to go over Jenkins/Dockerhub integration 2025-04-30
  - [ ] Stage deployment on d3-staging
    - [ ] Follow steps at https://altiusinstitute.slack.com/archives/D0B7HECUF/p1746556983503569 to pull in post-CI container
    - [x] Build number is at https://altiusinstitute.slack.com/archives/D0B7HECUF/p1746557046066119
    - [ ] Add conf.d entry at https://altiusinstitute.slack.com/archives/D0B7HECUF/p1746558487667099 
    - [ ] Reload https://altiusinstitute.slack.com/archives/D0B7HECUF/p1746558613219829
    - [ ] Test access to slurm-proxy host from within site network
  - [ ] Test stage with secrets
    - [x] Firewalling
    - [ ] JWT token
  - [ ] Can we submit a job on behalf of test user (`slurmapitest`)?
  - [ ] How much disk space is available for logs?
    - [ ] Log rolling