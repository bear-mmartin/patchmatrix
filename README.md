# patchmatrix

patchmatrix generates cross-version patches from git tags.  Useful for distributing software updates in the form of patch files.


## Installation


```bash
git clone https://github.com/bear-mmartin/patchmatrix.git
pip3 install GitPython
pip3 install semver
```

## Usage

```bash
python3 patchmatrix.py
```

Command line arguments are not yet supported.  For now, edit patchmatrix.py to configure.

The default configuration clones amzn/amazon-payments-magento-2-plugin and generates patches for compatible version pairs using the tags available in that repo, and writes the patches out to the `patches/` directory.
