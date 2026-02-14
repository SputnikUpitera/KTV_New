#!/bin/bash
killall vlc && sleep 1 && killall vlc && sleep 1
month=$(date '+%m')
day=$(date '+%d')

hour=$(date '+%H')
minutes=$(date '+%M')
echo $month/$day/$hour-$minutes >> ~/vlc_stop.log
