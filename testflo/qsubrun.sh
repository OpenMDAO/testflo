#!/bin/bash
#
# usage: mpirun -n [#] python mpirun.py [testspec] [host] [port] [key]
#
procs=$2
testspec=$5
cmd=${@:3}

name=${testspec##*\.}

jobfile="$name-$BASHPID.job"

echo "jobfile: $jobfile"
echo "numproc: $procs"
echo "command: $cmd"

echo "#!/bin/bash"         >$jobfile
echo "#$ -pe ompi $procs" >>$jobfile
echo "#$ -N $name"        >>$jobfile
echo "#$ -cwd"            >>$jobfile
echo "#$ -S /bin/bash"    >>$jobfile
echo "#$ -V"              >>$jobfile
echo "/hx/software/apps/openmpi/1.10.2/64bit/gnu/bin/mpirun -n \$NSLOTS $cmd" >>$jobfile

qsub $jobfile

#rm -f $jobfile
