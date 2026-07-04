#!/bin/bash -l

####################################
#     ARIS slurm script template   #
#                                  #
# Submit script: sbatch filename   #
#                                  #
####################################

#SBATCH --job-name=lscpu    # Job name
#SBATCH --output=lscpu.%j.out # Stdout (%j expands to jobId)
#SBATCH --error=lscpu.%j.err # Stderr (%j expands to jobId)
#SBATCH --ntasks=1     # Number of tasks(processes)
#SBATCH --nodes=1     # Number of nodes requested
#SBATCH --ntasks-per-node=1     # Tasks per node
#SBATCH --cpus-per-task=1     # Threads per task
#SBATCH --time=0:1:00   # walltime
#SBATCH --mem=1G   # memory per NODE
##SBATCH --mem-per-cpu=1024M   # memory per CPU core
#SBATCH --partition=compute    # Partition

if [ x$SLURM_CPUS_PER_TASK == x ]; then
  export OMP_NUM_THREADS=1
else
  export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
fi


## LOAD MODULES ##
module purge		# clean up loaded modules

# load necessary modules
module load gnu/13.3.0
module load openmpi/4.1.8/gnu

## RUN YOUR PROGRAM ##
srun lscpu -e=cpu,node,socket,core

