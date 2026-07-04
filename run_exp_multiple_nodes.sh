#!/bin/bash -l

####################################
#     ARIS slurm script template   #
#                                  #
# Submit script: sbatch filename   #
#                                  #
####################################

#SBATCH --job-name=jobname    # Job name
#SBATCH --output=%j.out # Stdout (%j expands to jobId)
#SBATCH --error=%j.err # Stderr (%j expands to jobId)
#SBATCH --ntasks=256     # Number of tasks(processes)
#SBATCH --nodes=2     # Number of nodes requested
#SBATCH --ntasks-per-node=128     # Tasks per node
#SBATCH --cpus-per-task=1     # Threads per task
#SBATCH --time=01:00:00   # walltime
#SBATCH --mem=496G   # memory per NODE
#SBATCH --partition=compute    # Partition
#SBATCH --exclusive

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
module load cuda/12.8.1

## RUN YOUR PROGRAM ##

bench="$1.$2.x"
map_modes=(
  "--map-by ppr:128:node --bind-to core"
  "--map-by ppr:64:node --bind-to core"
  "--map-by ppr:32:socket --bind-to core"
  "--map-by ppr:8:numa --bind-to core"
  "--map-by ppr:4:L3cache --bind-to core"
  "--map-by node -N 64 --bind-to core"
  "--map-by socket -N 64 --bind-to core"
  "--map-by numa -N 64 --bind-to core"
  "--map-by L3cache -N 64 --bind-to core"
)

for mode in "${map_modes[@]}"; do
  echo "### RUN: $mode $bench"
  mpirun $mode -np 128 ./numareport
  sleep 1
  mpirun $mode -np 128 ./NPB3.4-MPI/bin/$bench
  sleep 5
  mpirun $mode -np 128 ./NPB3.4-MPI/bin/$bench
  sleep 5
  mpirun $mode -np 128 ./NPB3.4-MPI/bin/$bench
  sleep 5
done


