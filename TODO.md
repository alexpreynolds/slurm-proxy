# hpc-proxy

### In Progress

- [ ] Task submission #feat @alexpreynolds
  - [ ] Replace SSH-based job submission process with RESTful call that targets specified end user and new cluster partition
    - [x] Preliminary job to create destination folders for output and error logs, before firing primary task
    - [ ] Main job fired off after preliminary prep job is completed (use `job_id` as dependency)
    - [ ] Test overall task submission against `areynolds` etc.

- [ ] Task SLURM REST endpoints @alexpreynolds
  - [x] Test `slurm/jobs/` and `slurmdb/job/<job_id>/` endpoints
    - [x] Ask Matt to resolve issue with `slurmdb/job/<job_id>/`
  - [ ] Modify `slurmdb/job/<job_id>/` endpoint to return structured object containing information provided by CLI `sacct -j <job_id> --format=JobID,Jobname%-128,state,User,partition,time,start,end,elapsed` call
  - [ ] Modify `slurm/jobs/` endpoint to return all jobs metadata associated with specified end user

- [ ] Task monitoring #feat @alexpreynolds
  - [ ] Modify `get_current_slurm_job_metadata_by_slurm_job_id` and similar fns to support RESTful calls in addition to SSH calls
  - [ ] Test RESTful monitoring
  - [ ] MongoDB database backup strategy
    - [ ] Definition
    - [ ] Implementation as part of Docker distribution
  - [ ] Test how app behaves if mongodb service is brought down
    - [ ] Decide how to report errors

- [ ] Docker deployment #feat @alexpreynolds
  - [x] Modify Dockerfile and test w/o environment variables 2025-04-29
  - [ ] Meet with Mike to go over Jenkins/Dockerhub integration 2025-04-30
  - [ ] Stage deployment
  - [ ] Test stage with secrets
    - [ ] Firewalling
    - [ ] JWT token