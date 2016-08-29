#!/bin/bash
#
# usage: qsubrun [-n #] python [isolatedrun.py|mpirun.py] [testspec] [host port key]
#

echo
echo
echo "qsubrun.sh received command:"
echo $*
echo
echo


# defaults
procs=1
mpi=0

# process args
while [[ $# > 0 ]]; do
    arg="$1"

    case $arg in
        -n)
            procs=$2
            echo "numproc: $procs"
            shift
            shift
            cmd=${@:1}
            echo "cmd: $cmd"
            testspec=$3
            echo "testspec: $testspec"
            ;;
        *)
            shift
            ;;
    esac
done


name=${testspec##*\.}

jobfile="$name-$BASHPID.job"

echo
echo
echo "jobfile: $jobfile"
echo "numproc: $procs"
echo "mpi: $mpi"
echo "name: $name"
echo "command: $cmd"

echo "#!/bin/bash"         >$jobfile
echo "#$ -N $name"        >>$jobfile
echo "#$ -cwd"            >>$jobfile
echo "#$ -S /bin/bash"    >>$jobfile
echo "#$ -V"              >>$jobfile
if (( $procs > 1 )) ; then
    echo "#$ -pe ompi $procs" >>$jobfile
    echo "/hx/software/apps/openmpi/1.10.2/64bit/gnu/bin/mpirun -n \$NSLOTS $cmd" >>$jobfile
else
    echo "$cmd" >>$jobfile
fi
  

cat $jobfile
qsub $jobfile

#rm -f $jobfile
