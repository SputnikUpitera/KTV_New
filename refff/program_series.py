import os, av
import subprocess
import datetime

def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)
    
def get_length_dir(dirname):
    length = 0
    print("dirname: ", dirname)

    for dirpath, dirnames, filenames in os.walk(dirname):
        for filename in filenames:
            length = get_length(os.path.join(dirpath, filename)) + length
    return length/60
    
def destinationPath(daysNumber):
    day_delta = datetime.timedelta(days=1)
    start_date = datetime.date.today()

    destination = os.path.join((start_date + daysNumber*day_delta).strftime("%m"), (start_date + daysNumber*day_delta).strftime("%d"), time)
    return destination
    
# os.chdir("films")

files = []
# names = []
duration = []
totalDuration = []
time = '14-30'
# максимальная продолжительность слота в минутах
slot = 150
daysNumber = 0

# end_date = start_date + 7*day_delta
length = 1
while length:
    destination = destinationPath(daysNumber)
    if not os.path.isdir(destination):
        break
    length = get_length_dir(destination)
    if not length:
        break

    for dirpath, dirnames, filenames in os.walk('series/Justified/'):
        for filename in sorted(filenames):
            fileLength = get_length(os.path.join(dirpath, filename))/60

            print("filename:", filename)
            print("Directory length:", "%.2f" % length)
            print("Need less then:", "%.2f" % (slot - length))
            print("Cheking:", os.path.join(dirpath, filename))
            print("File length: ", "%.2f" % fileLength)
            # print("(length + fileLength):", (length + fileLength))
            print("---------------")
            if (length + fileLength) >= slot :
                print("continue")
                break

            # length = 0
            print("____Moving____")
            os.replace(os.path.join(dirpath, filename), os.path.join(destination, '3.' + filename))
            break
    daysNumber = daysNumber + 1
