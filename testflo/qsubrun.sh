#!/bin/bash
#
# usage: qsubrun -n # python script testspec host port key
#

#
# process args
#
procs=$2
cmd=${@:3}
testspec=$5

#
# build job name from testspec
#
name=${testspec##*\.}
jobfile="$name-$BASHPID.job"

#
# build job script
#
echo "#!/bin/bash"         >$jobfile
echo "#$ -N $name"        >>$jobfile
echo "#$ -cwd"            >>$jobfile
echo "#$ -S /bin/bash"    >>$jobfile
echo "#$ -V"              >>$jobfile
if (( $procs > 1 )) ; then
    echo "#$ -pe ompi $procs" >>$jobfile
    echo "mpirun -n \$NSLOTS $cmd" >>$jobfile
else
    echo "$cmd" >>$jobfile
fi
  
#
# submit job using qsub
#
cat $jobfile
qsub $jobfile

#
# clean up
#
#rm -f $jobfile
