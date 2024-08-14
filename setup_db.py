import os
import glob
import subprocess

# Specify the root directory where you want to start searching
root_directory = '/Users/dpwillis/code/testudo'

# Use glob to find all JSON files in the root directory and its sub-directories
json_files = glob.glob(os.path.join(root_directory, '**/*.json'), recursive=True)

# Iterate over the list of JSON files and print their filenames
for json_file in json_files:
    command = ['sqlite-utils', 'insert', 'testudo.db', 'courses', json_file, '--flatten']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
