#!/bin/bash -l

####################################
#     ARIS slurm script template   #
#                                  #
# Submit script: sbatch filename   #
#                                  #
####################################

#SBATCH --job-name=spatman # Job name
#SBATCH --output=%j.out # Stdout (%j expands to jobId)
#SBATCH --error=%j.err # Stderr (%j expands to jobId)
######SBATCH --ntasks=128     # Number of tasks(processes)
#SBATCH --nodes=1     # Number of nodes requested
#SBATCH --cpus-per-task=1     # Threads per task
#SBATCH --time=04:59:00   # walltime
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

## RUN YOUR PROGRAM ##

bench="$1.$2.x"
config_list="$3"

# ---- CONFIGURATIONS ----

declare -A MAP_MODE
MAP_MODE[half_node]="--map-by ppr:64:socket --bind-to core"
MAP_MODE[half_socket_RR]="--map-by socket --bind-to core"
MAP_MODE[half_socket_IO]="--map-by ppr:32:socket --bind-to core"
MAP_MODE[half_numa_RR]="--map-by numa --bind-to core"
MAP_MODE[half_numa_IO]="--map-by ppr:8:numa --bind-to core"
MAP_MODE[half_ccd_RR]="--map-by L3cache --bind-to core"
MAP_MODE[half_ccd_IO]="--map-by ppr:4:L3cache --bind-to core"

all_configs=(
  "half_node"
  "half_socket_RR"
  "half_socket_IO"
  "half_numa_RR"
  "half_numa_IO"
  "half_ccd_RR"
  "half_ccd_IO"
)

# $3: optional comma-separated subset of the configs above (e.g. "half_node,half_ccd_RR").
# If omitted, all configs are run.
if [ -n "$config_list" ]; then
  IFS=',' read -ra configs <<< "$config_list"
  for config in "${configs[@]}"; do
    if [[ ! " ${all_configs[*]} " =~ " ${config} " ]]; then
      echo "Unknown config: $config" >&2
      echo "Valid configs: ${all_configs[*]}" >&2
      exit 1
    fi
  done
else
  configs=("${all_configs[@]}")
fi

for config in "${configs[@]}"; do
  mode=${MAP_MODE[$config]}
  echo "# RUN: $mode $bench"
  mpirun $mode -np 64 ./numareport
  sleep 1
  mpirun $mode -np 64 ./NPB3.4-MPI/bin/$bench
  sleep 5
  mpirun $mode -np 64 ./NPB3.4-MPI/bin/$bench
  sleep 5
  mpirun $mode -np 64 ./NPB3.4-MPI/bin/$bench
  sleep 5
done

