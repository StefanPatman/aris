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

bench1="$1.$2.x"
bench2="$3.$4.x"
repetitions="${5:-3}"
config_list="$6"

# ---- GENERATE RANKFILES ----

node=$SLURMD_NODENAME
declare -A RF1 RF2

# Config: half_node_IO — proc1: cores 0-63, proc2: cores 64-127
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 63); do
  echo "rank $i=$node slot=$i"        >> $rf1
  echo "rank $i=$node slot=$((i+64))" >> $rf2
done
RF1[half_node_IO]=$rf1; RF2[half_node_IO]=$rf2

# Config: half_socket_IO — proc1: cores 0-31+64-95 (NUMAs 0,1,4,5), proc2: cores 32-63+96-127 (NUMAs 2,3,6,7)
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 31); do
  echo "rank $i=$node slot=$i"                    >> $rf1
  echo "rank $((i+32))=$node slot=$((i+64))"      >> $rf1
  echo "rank $i=$node slot=$((i+32))"             >> $rf2
  echo "rank $((i+32))=$node slot=$((i+96))"      >> $rf2
done
RF1[half_socket_IO]=$rf1; RF2[half_socket_IO]=$rf2

# Config: half_numa_IO — proc1: cores 0-7,16-23,... (first 8 of each NUMA), proc2: cores 8-15,24-31,...
rf1=$(mktemp); rf2=$(mktemp)
rank=0
for numa in $(seq 0 7); do
  base=$((numa * 16))
  for i in $(seq 0 7); do
    echo "rank $rank=$node slot=$((base + i))"     >> $rf1
    echo "rank $rank=$node slot=$((base + 8 + i))" >> $rf2
    rank=$((rank + 1))
  done
done
RF1[half_numa_IO]=$rf1; RF2[half_numa_IO]=$rf2

# Config: half_ccd_IO — proc1: cores 0-3,8-11,... (first 4 of each CCD), proc2: cores 4-7,12-15,...
rf1=$(mktemp); rf2=$(mktemp)
rank=0
for ccd in $(seq 0 15); do
  base=$((ccd * 8))
  for i in $(seq 0 3); do
    echo "rank $rank=$node slot=$((base + i))"     >> $rf1
    echo "rank $rank=$node slot=$((base + 4 + i))" >> $rf2
    rank=$((rank + 1))
  done
done
RF1[half_ccd_IO]=$rf1; RF2[half_ccd_IO]=$rf2

# ---- ROUND ROBIN CONFIGS (to be filled) ----

# Config: half_node_RR — proc1: even cores 0,2,4,...,126; proc2: odd cores 1,3,5,...,127
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 63); do
  echo "rank $i=$node slot=$((i*2))"     >> $rf1
  echo "rank $i=$node slot=$((i*2+1))"  >> $rf2
done
RF1[half_node_RR]=$rf1; RF2[half_node_RR]=$rf2

# Config: half_socket_RR — proc1: RR over cores 0-31,64-95; proc2: RR over cores 32-63,96-127
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 31); do
  echo "rank $((i*2))=$node slot=$i"           >> $rf1
  echo "rank $((i*2+1))=$node slot=$((i+64))"  >> $rf1
  echo "rank $((i*2))=$node slot=$((i+32))"    >> $rf2
  echo "rank $((i*2+1))=$node slot=$((i+96))"  >> $rf2
done
RF1[half_socket_RR]=$rf1; RF2[half_socket_RR]=$rf2

# Config: half_numa_RR — proc1: RR over first 8 cores of each NUMA (0,16,32,...,1,17,33,...); proc2: RR over second 8 (8,24,40,...)
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 7); do
  for numa in $(seq 0 7); do
    rank=$((i*8 + numa))
    echo "rank $rank=$node slot=$((numa*16 + i))"     >> $rf1
    echo "rank $rank=$node slot=$((numa*16 + 8 + i))" >> $rf2
  done
done
RF1[half_numa_RR]=$rf1; RF2[half_numa_RR]=$rf2

# Config: half_ccd_RR — proc1: RR over first 4 cores of each CCD (0,8,16,...); proc2: RR over second 4 (4,12,20,...)
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 3); do
  for ccd in $(seq 0 15); do
    rank=$((i*16 + ccd))
    echo "rank $rank=$node slot=$((ccd*8 + i))"     >> $rf1
    echo "rank $rank=$node slot=$((ccd*8 + 4 + i))" >> $rf2
  done
done
RF1[half_ccd_RR]=$rf1; RF2[half_ccd_RR]=$rf2

# ---- CONFIGURATIONS ----

all_configs=(
  "half_node_IO"
  "half_socket_IO"
  "half_numa_IO"
  "half_ccd_IO"
  "half_node_RR"
  "half_socket_RR"
  "half_numa_RR"
  "half_ccd_RR"
)

# $6: optional comma-separated subset of the configs above (e.g. "half_node_IO,half_ccd_RR").
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

# ---- HELPERS ----

run_bench() {
  local rf=$1
  local bench=$2
  local my_count=$3
  local other_count=$4
  local out=$5
  local err=$6
  local count=0

  while true; do
    count=$((count + 1))
    echo "### mpirun $count $(date '+%Y-%m-%d %H:%M:%S')" | tee -a $out $err
    mpirun --rankfile $rf --bind-to core -np 64 --report-bindings ./NPB3.4-MPI/bin/$bench >>$out 2>>$err
    echo $count > $my_count
    if [ $count -ge $repetitions ] && [ $(cat $other_count) -ge $repetitions ]; then
      break
    fi
  done
}

# ---- RUN ----

for config in "${configs[@]}"; do
  rf1=${RF1[$config]}
  rf2=${RF2[$config]}
  echo "# RUN: $config $bench1 $bench2"
  echo "# RUN: $config $bench1 $bench2" >&2
  echo "## RANKFILE 1:"
  cat $rf1
  echo "## RANKFILE 2:"
  cat $rf2
  echo "## REPORT 1:"
  mpirun --rankfile $rf1 --bind-to core -np 64 --report-bindings ./numareport
  echo "## REPORT 2:"
  mpirun --rankfile $rf2 --bind-to core -np 64 --report-bindings ./numareport
  echo "## EXECUTE:"
  cnt1=$(mktemp); echo 0 > $cnt1
  cnt2=$(mktemp); echo 0 > $cnt2
  out1=$(mktemp); err1=$(mktemp)
  out2=$(mktemp); err2=$(mktemp)
  run_bench $rf1 $bench1 $cnt1 $cnt2 $out1 $err1 &
  run_bench $rf2 $bench2 $cnt2 $cnt1 $out2 $err2 &
  wait
  echo "## BENCH 1:"; cat $out1
  echo "## BENCH 2:"; cat $out2
  echo "## BENCH 1:" >&2; cat $err1 >&2
  echo "## BENCH 2:" >&2; cat $err2 >&2
  rm -f $cnt1 $cnt2 $out1 $err1 $out2 $err2
done

for config in "${all_configs[@]}"; do
  rm -f ${RF1[$config]} ${RF2[$config]}
done

