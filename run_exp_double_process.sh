#!/bin/bash -l

####################################
#     ARIS slurm script template   #
#                                  #
# Submit script: sbatch filename   #
#                                  #
####################################

#SBATCH --job-name=script # Job name
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

# ---- GENERATE RANKFILES ----

node=$SLURMD_NODENAME
declare -A RF1 RF2

# Config: half_node — proc1: cores 0-63, proc2: cores 64-127
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 63); do
  echo "rank $i=$node slot=$i"        >> $rf1
  echo "rank $i=$node slot=$((i+64))" >> $rf2
done
RF1[half_node]=$rf1; RF2[half_node]=$rf2

# Config: half_socket — proc1: cores 0-31+64-95 (NUMAs 0,1,4,5), proc2: cores 32-63+96-127 (NUMAs 2,3,6,7)
rf1=$(mktemp); rf2=$(mktemp)
for i in $(seq 0 31); do
  echo "rank $i=$node slot=$i"                    >> $rf1
  echo "rank $((i+32))=$node slot=$((i+64))"      >> $rf1
  echo "rank $i=$node slot=$((i+32))"             >> $rf2
  echo "rank $((i+32))=$node slot=$((i+96))"      >> $rf2
done
RF1[half_socket]=$rf1; RF2[half_socket]=$rf2

# Config: half_numa — proc1: cores 0-7,16-23,... (first 8 of each NUMA), proc2: cores 8-15,24-31,...
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
RF1[half_numa]=$rf1; RF2[half_numa]=$rf2

# Config: half_ccd — proc1: cores 0-3,8-11,... (first 4 of each CCD), proc2: cores 4-7,12-15,...
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
RF1[half_ccd]=$rf1; RF2[half_ccd]=$rf2

# ---- CONFIGURATIONS ----

configs=(
  "half_node"
  "half_socket"
  "half_numa"
  "half_ccd"
)

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
    mpirun --rankfile $rf --bind-to core -np 64 ./NPB3.4-MPI/bin/$bench >>$out 2>>$err
    count=$((count + 1))
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
  echo "### RUN: $config $bench1 $bench2"
  echo "# RANKFILE 1:"
  cat $rf1
  echo "# RANKFILE 2:"
  cat $rf2
  echo "# REPORT 1:"
  mpirun --rankfile $rf1 --bind-to core -np 64 ./numareport
  echo "# REPORT 2:"
  mpirun --rankfile $rf2 --bind-to core -np 64 ./numareport
  echo "# EXECUTE:"
  cnt1=$(mktemp); echo 0 > $cnt1
  cnt2=$(mktemp); echo 0 > $cnt2
  out1=$(mktemp); err1=$(mktemp)
  out2=$(mktemp); err2=$(mktemp)
  run_bench $rf1 $bench1 $cnt1 $cnt2 $out1 $err1 &
  run_bench $rf2 $bench2 $cnt2 $cnt1 $out2 $err2 &
  wait
  echo "# BENCH 1:"; cat $out1
  echo "# BENCH 2:"; cat $out2
  echo "# BENCH 1:" >&2; cat $err1 >&2
  echo "# BENCH 2:" >&2; cat $err2 >&2
  rm -f $cnt1 $cnt2 $out1 $err1 $out2 $err2
done

for config in "${configs[@]}"; do
  rm -f ${RF1[$config]} ${RF2[$config]}
done

