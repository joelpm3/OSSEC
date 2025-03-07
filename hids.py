#!/usr/bin/python3

import json
import argparse
import enum
import os
import stat
import hashlib


# database dictionary structure:
# {
#    "/path/to/file/file1.txt" :
#    {
#        "type": "f",
#        "uid": 1234,
#        "gid": 1234,
#        "mode": 0o644,
#        "size": 1440000,
#        "hash": "0123456789ABCDEF"
#    },
#    "/path/to/dir1" :
#    {
#        "type": "d",
#        "uid": 1234,
#        "gid": 1234,
#        "mode": 0o755
#    },
#    ...
# }


Actions = ['count', 'add', 'hash', 'check', 'verify', 'update']


# --- Action 1: count ---

# print the number of files and directories in the specified path and/or database
def count(data, files, directories):
    # count files in database, skip if no database given
    if data != None:
        f=0
        d=0
        for entry in data:
            if data[entry]['type'] == 'f':
                f+=1
            elif data[entry]['type'] == 'd':
                d+=1
        print(f'database contains {f} files and {d} directories')
    # count files and dirs, skip if no files and no directories given (empty list = boolean False)
    if files or directories:
        # get the number of items in the list of files
        f=len(files)
        d=len(directories)
        print(f'path contains {f} files and {d} directories')
    # success
    return True


# --- Action 2: add ---

# add files and directories that are not in the database yet to the database
def add(data, files, directories):
    # handle list of files
    for fpath in files:
        # check whether file is already in the database
        if not fpath in data:
            # add the properties of the file to the database
            data[fpath] = filedata(fpath)
        # if a file path is already in the database, you should use check or update
        else:
            print(f'file already in database: {fpath}')
            print('use check or update action')
            return False
    # handle list of directories
    for dpath in directories:
        # check whether directory is already in the database
        if not dpath in data:
            # add the properties of the directory to the database
            data[dpath] = dirdata(dpath)
        # if a directory path is already in the database, you should use check or update
        else:
            print(f'directory already in database: {dpath}')
            print('use check or update action')
            return False
    print('add: success')
    # output file count in database
    count(data, None, None)
    return True

# return a dictionary with information about a directory
def dirdata(dpath):
    assert os.path.isdir(dpath)

    # initialize new empty dictionary for the directory's properties.
    dir_properties = {}

    # type for directory is 'd'
    dir_properties['type'] = 'd'

    # Get file stats
    stats = os.stat(dpath)
    
    # Add user ID
    dir_properties['uid'] = stats.st_uid
    
    # Add group ID
    dir_properties['gid'] = stats.st_gid
    
    # Add permissions (mode) in octal representation
    dir_properties['mode'] = oct(stat.S_IMODE(stats.st_mode))

    # finally, return the dictionary
    return dir_properties

# return a dictionary with information about a file
def filedata(fpath):
    assert os.path.isfile(fpath)

    # initialize new empty dictionary for the file's properties.
    file_properties = {}

    # type for file is 'f'
    file_properties['type'] = 'f'

    # Get file stats
    stats = os.stat(fpath)
    
    # Add user ID
    file_properties['uid'] = stats.st_uid
    
    # Add group ID
    file_properties['gid'] = stats.st_gid
    
    # Add permissions (mode) in octal representation
    file_properties['mode'] = oct(stat.S_IMODE(stats.st_mode))
    
    # Add file size
    file_properties['size'] = stats.st_size

    # finally, return the dictionary
    return file_properties


# --- Action 3: hash ---

# add checksum for files (not directories) to database entries
# this function is not called "hash" because python has a built-in function with that name
def cksum(data, files, directories):
    # Count how many hashes were calculated
    hash_count = 0
    
    # Process only files, not directories
    for fpath in files:
        # Check if file exists in database
        if fpath not in data:
            print(f"Error: File not in database: {fpath}")
            print("Use add action to add files first")
            return False
        
        # Check if hash already exists
        if 'hash' in data[fpath]:
            print(f"Error: Hash already exists for: {fpath}")
            print("Use update action to reset hash")
            return False
        
        # Calculate and add hash
        data[fpath]['hash'] = sha256file(fpath)
        hash_count += 1
    
    print(f"Added hashes for {hash_count} files")
    return True


# --- Action 4: update ---

# update database entries that have changed
def update(data, files, directories):
    # Keep track of changes
    new_count = 0
    changed_count = 0
    removed_hash_count = 0
    removed_entry_count = 0
    
    # Check which entries in database no longer exist in filesystem
    to_remove = []
    for entry in data:
        if entry not in files and entry not in directories:
            to_remove.append(entry)
    
    # Remove entries that no longer exist
    for entry in to_remove:
        del data[entry]
        removed_entry_count += 1
    
    # Update or add files
    for fpath in files:
        if fpath not in data:
            # New file
            data[fpath] = filedata(fpath)
            new_count += 1
        else:
            # Existing file - update values
            new_data = filedata(fpath)
            # Check if anything changed
            changed = False
            for key in new_data:
                if key not in data[fpath] or data[fpath][key] != new_data[key]:
                    changed = True
            
            # Update all attributes
            data[fpath].update(new_data)
            
            # Remove hash if present
            if 'hash' in data[fpath]:
                del data[fpath]['hash']
                removed_hash_count += 1
            
            if changed:
                changed_count += 1
    
    # Update or add directories
    for dpath in directories:
        if dpath not in data:
            # New directory
            data[dpath] = dirdata(dpath)
            new_count += 1
        else:
            # Existing directory - update values
            new_data = dirdata(dpath)
            # Check if anything changed
            changed = False
            for key in new_data:
                if key not in data[dpath] or data[dpath][key] != new_data[key]:
                    changed = True
            
            # Update all attributes
            data[dpath].update(new_data)
            
            if changed:
                changed_count += 1
    
    # Print summary
    print(f"Added {new_count} new entries")
    print(f"Updated {changed_count} entries")
    print(f"Removed {removed_hash_count} hashes")
    print(f"Removed {removed_entry_count} deleted entries")
    
    return True


# --- Action 5: verify ---

# check files in path against database entries
# check correct hash for files that have a hash in the database
def verify(data, files, directories):
    # Count issues by type
    missing_count = 0
    new_count = 0
    mismatch_count = 0
    hash_changed_count = 0
    
    # Check if entries in database still exist
    for entry in data:
        if entry not in files and entry not in directories:
            print(f"Warning: missing {entry}")
            missing_count += 1
    
    # Check files
    for fpath in files:
        # New file?
        if fpath not in data:
            print(f"Warning: new file {fpath}")
            new_count += 1
            continue
            
        # Check if type changed (from directory to file)
        if data[fpath]["type"] != "f":
            print(f"Warning: mismatch {fpath}")
            print(f"  type changed from {data[fpath]['type']} to f")
            mismatch_count += 1
            continue
            
        # Check file attributes
        current = filedata(fpath)
        has_mismatch = False
        
        for key in current:
            if key in data[fpath] and current[key] != data[fpath][key]:
                if not has_mismatch:
                    print(f"Warning: mismatch {fpath}")
                    has_mismatch = True
                    mismatch_count += 1
                print(f"  {key} changed from {data[fpath][key]} to {current[key]}")
        
        # Check hash if present
        if "hash" in data[fpath]:
            current_hash = sha256file(fpath)
            if current_hash != data[fpath]["hash"]:
                print(f"Warning: hash changed {fpath}")
                print(f"  hash changed from {data[fpath]['hash']} to {current_hash}")
                hash_changed_count += 1
    
    # Check directories
    for dpath in directories:
        # New directory?
        if dpath not in data:
            print(f"Warning: new directory {dpath}")
            new_count += 1
            continue
            
        # Check if type changed (from file to directory)
        if data[dpath]["type"] != "d":
            print(f"Warning: mismatch {dpath}")
            print(f"  type changed from {data[dpath]['type']} to d")
            mismatch_count += 1
            continue
            
        # Check directory attributes
        current = dirdata(dpath)
        has_mismatch = False
        
        for key in current:
            if key in data[dpath] and current[key] != data[dpath][key]:
                if not has_mismatch:
                    print(f"Warning: mismatch {dpath}")
                    has_mismatch = True
                    mismatch_count += 1
                print(f"  {key} changed from {data[dpath][key]} to {current[key]}")
    
    # Print summary of issues if any were found
    total_issues = missing_count + new_count + mismatch_count + hash_changed_count
    if total_issues > 0:
        print(f"\nSummary of issues:")
        if missing_count > 0:
            print(f"  {missing_count} entries missing")
        if new_count > 0:
            print(f"  {new_count} new entries")
        if mismatch_count > 0:
            print(f"  {mismatch_count} entries with attribute mismatches")
        if hash_changed_count > 0:
            print(f"  {hash_changed_count} entries with hash changes")
        return False
    
    print("No issues found")
    return True


# --- helper functions ---

# return the SHA256 hash of a file
def sha256file(fpath):
    # only works with files, not directories
    assert os.path.isfile(fpath)
    # read file in 16k blocks
    BUFSIZE = 16384
    # initialize sha256 hash object
    s256 = hashlib.sha256()
    # open file for reading and read first block
    f = open(fpath, 'rb')
    buffer = f.read(BUFSIZE)
    # read block and update hash
    while len(buffer) > 0:
        s256.update(buffer)
        buffer = f.read(BUFSIZE)
    f.close()
    # return string containing hexdigit representation of hash
    return s256.hexdigest()


# --- database functions ---

# save database from dictionary to file
def save_db(dbfile, dict):
    jsondata = json.dumps(dict, indent=4)
    f = open(dbfile,"w")
    f.write(jsondata)
    f.close()

# read database from file into dictionary
def read_db(dbfile):
    f = open(dbfile,"r")
    dict = json.loads(f.read())
    f.close()
    return dict


# --- main function ---

def main():
    # parse commandline arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--database')
    parser.add_argument('-p', '--path')
    parser.add_argument('action', choices=Actions)
    args = parser.parse_args()

    # --- database directory setup ---

    # database is needed for add,hash,check/verify,update
    if args.action in ['add','hash','check','verify','update'] and args.database == None:
        print(f'action {args.action} needs database argument')
        return 1

    # load existing contents from database file
    data = None
    # if database is given but not a file, it's created later when writing back
    if args.database != None and os.path.isfile(args.database):
        data = read_db(args.database)

    # initialize empty dictionary if database is given
    if data == None and args.database != None:
        data = {}


    # --- file and directories list setup ---

    path = None
    file_list = []
    directory_list = []

    if args.path == None:
        # path is needed for add,hash,check/verify,update
        if args.action in ['add','hash','check','verify','update']:
            print(f'action {args.action} needs path argument')
            return 1
    else:
        # verify path is a file or directory
        if not os.path.isdir(args.path) and not os.path.isfile(args.path):
            raise argparse.ArgumentTypeError(f'{args.path} is not a valid file or directory')
        # normalize path
        path = os.path.abspath(args.path)

        # single file => add to file list
        if os.path.isfile(path):
            file_list.append(path)
        else:
            # add root directory
            directory_list.append(path)
            # get list of subdirectories and files
            for root,dirs,files in os.walk(path):
                for item in dirs:
                    # get full path
                    dpath = os.path.join(root,item)
                    directory_list.append(dpath)
                for item in files:
                    # get full path
                    fpath = os.path.join(root,item)
                    # could be link or special device instead of file, we ignore those
                    if os.path.isfile(fpath):
                        file_list.append(fpath)

    # --- run desired action ---

    r = False
    if args.action == 'count':
        r = count(data, file_list, directory_list)
    elif args.action == 'add':
        r = add(data, file_list, directory_list)
    elif args.action == 'hash':
        r = cksum(data, file_list, directory_list)
    elif args.action == 'verify' or args.action == 'check':
        r = verify(data, file_list, directory_list)
    elif args.action == 'update':
        r = update(data, file_list, directory_list)

    if not r:
        print(f'there was a problem running action {args.action}')
        return 1

    # save (possibly changed) database again
    if data != None and args.database != None:
        save_db(args.database, data)

    return 0

if __name__ == "__main__":
    main()

