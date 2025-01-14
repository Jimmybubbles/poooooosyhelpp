import os
import shutil

def clear_folder(folder_path):
    """
    Clear all files and subdirectories in the given folder.
    
    :param folder_path: Path to the folder to be cleared
    """
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

# List of folders you want to clear
folders_to_clear = [
    r'C:\Users\James\poosy\poooooosyhelpp\watchlist_Scanner\results',
    r'C:\Users\James\poosy\poooooosyhelpp\watchlist_Scanner\updatedResults'
]

# Clear each folder
for folder in folders_to_clear:
    if os.path.exists(folder):
        clear_folder(folder)
        print(f'Cleared contents of: {folder}')
    else:
        print(f'Warning: {folder} does not exist.')

print("Cleanup completed.")