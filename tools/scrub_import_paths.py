"""Remove machine-specific import paths from imported assets (textures, meshes) and resave them.

Run headless:
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Also imported by tools/import_world_kit.py, import_landmarks.py and import_dragon.py (scrub(asset) after import).

Why: PNG textures are imported by Interchange, which keeps its import graph in the asset's import data, keyed by
the absolute source path (e.g. "Factory_C:/Users/<you>/..."). That puts the importing user's name into every
texture .uasset in Git. We replace the import data with a plain one holding only the project-relative source
file name (what "Reimport" needs), so the pixels and every other setting stay as they are.
"""
import os
import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
FOLDERS = ['/Game/DragonRider/World', '/Game/DragonRider/Characters']


def relative_source(asset):
    """The project-relative source path the asset was imported from, or '' if unknown."""
    data = asset.get_editor_property('asset_import_data')
    if not data:
        return ''
    files = list(data.extract_filenames())
    if not files:
        return ''
    full = unreal.Paths.convert_relative_path_to_full(files[0])
    rel = os.path.relpath(full, PROJECT_DIR).replace('\\', '/')
    return '' if rel.startswith('..') else rel


def scrub(asset):
    """Replace the asset's import data with a clean, relative one (C++ UDragonAssetLibrary.ResetImportData: the
    property is read-only from Python). Returns True if the asset changed."""
    rel = relative_source(asset)
    src = os.path.join(PROJECT_DIR, rel).replace(os.sep, '/') if rel else ''
    return bool(unreal.DragonAssetLibrary.reset_import_data(asset, src))


def scrub_folders(folders=FOLDERS):
    eal = unreal.EditorAssetLibrary
    n = 0
    for folder in folders:
        if not eal.does_directory_exist(folder):
            continue
        for path in eal.list_assets(folder, recursive=True, include_folder=False):
            a = eal.load_asset(path)
            if isinstance(a, (unreal.Texture, unreal.StaticMesh, unreal.SkeletalMesh, unreal.AnimSequence)) and scrub(a):
                eal.save_loaded_asset(a, False)
                n += 1
    unreal.log('SCRUB_IMPORT_PATHS: rewrote import data of %d assets' % n)
    return n


if __name__ == '__main__':
    scrub_folders()
