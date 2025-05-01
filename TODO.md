# hpc-proxy

### In Progress

- [ ] Task submission #feat @alexpreynolds
  - [x] Replace SSH-based job submission process with RESTful call that targets specified end user and new cluster partition
    - [x] Preliminary job to create destination folders for output and error logs, before firing primary task
    - [x] Main job fired off after preliminary prep job is completed (use `job_id` as dependency)
  - [ ] Run basic test with different users
    - [x] Test overall task submission against `areynolds`
    - [ ] Test overall task submission against another user account that can access the cluster

- [x] Task SLURM REST endpoints @alexpreynolds
  - [x] Test `slurm/jobs/` and `slurmdb/job/<job_id>/` endpoints
    - [x] Ask Matt to resolve issue with `slurmdb/job/<job_id>/`
  - [x] Modify `slurm/jobs/` endpoint to return all jobs metadata associated with specified end user and newer than update_time

- [x] Task monitoring #feat @alexpreynolds
  - [x] Modify `get_current_slurm_job_metadata_by_slurm_job_id` and similar fns to support RESTful calls in addition to SSH calls
  - [x] Test RESTful monitoring (submit job, query endpoints before and after state change)

- [ ] MongoDB database backup strategy
  - [ ] Definition
  - [ ] Implementation as part of Docker distribution
  - [ ] Test how app behaves if mongodb service is brought down
    - [ ] Decide how to report errors

- [ ] General
  - [ ] Replace remaining print statements with logger calls and set level (DEBUG)

- [ ] Docker deployment #feat @alexpreynolds
  - [x] Modify Dockerfile and test w/o environment variables 2025-04-29
  - [x] Meet with Mike to go over Jenkins/Dockerhub integration 2025-04-30
  - [ ] Stage deployment on d3-staging
  - [ ] Test stage with secrets
    - [ ] Firewalling
    - [ ] JWT token
  - [ ] How much disk space is available for logs?
    - [ ] Log rolling