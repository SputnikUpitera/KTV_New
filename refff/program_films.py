import os, av
import subprocess
import datetime

def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
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
slot = 140
daysNumber = 6

# end_date = start_date + 7*day_delta

for dirpath, dirnames, filenames in os.walk('series/mmm/'):
    length = 0
    totalLength = 0
    duration = []
    for filename in sorted(filenames):
        destination = destinationPath(daysNumber)
        if not os.path.isdir(destination):
            os.makedirs(destination)
            print("Created: ", destination)

        fileLength = get_length(os.path.join(dirpath, filename))/60
        if not length:
            length = get_length_dir(destination)

        print("filename: ", filename)
        print("Directory length: ", length)
        print("File length: ", fileLength)
        print("Need less then: ", slot - length)
        print("(length + fileLength): ", (length + fileLength))
        print("---------------")
        if (length + fileLength) >= slot :
            print("break")
            break

        length = 0

        os.replace(os.path.join(dirpath, filename), os.path.join(destination, '0.' + filename))
        daysNumber = daysNumber + 1
