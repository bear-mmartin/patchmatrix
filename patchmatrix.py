#!/usr/bin/env python3
from git import Repo, NoSuchPathError, InvalidGitRepositoryError
import itertools
import semver
import sys
import os

## Defines a subdirectory within the repository to be used for generating module-relative patches
class ModuleGroup:
    def __init__(self, moduleName, prefix):
        self.moduleName = moduleName
        self.prefix = prefix

class ModuleDiffProcessor:
    def __init__(self, moduleGroups=[]):
        self.moduleGroups = moduleGroups
    def _matchPath(self, path):
        for moduleGroup in self.moduleGroups:
            if path.startswith(moduleGroup.prefix):
                return moduleGroup
        return None
    def processPath(self, path):
        if not path:
            return None
        moduleGroup = self._matchPath(path)
        if moduleGroup:
#            return path.replace(moduleGroup.prefix, moduleGroup.moduleName, 1)
            return path[len(moduleGroup.prefix)+1:]
        return path
    def tag(self, diff):
        path = diff.b_path if diff.b_path else diff.a_path
        moduleGroup = self._matchPath(path)
        if not moduleGroup:
            raise Exception('Could not identify module for %s' % (path))
        return (moduleGroup.moduleName,)

class PatchMatrix:
    def __init__(self, repoUrl=None, compatSets=[], path=None, diffProcessor=None):
        self.path = path if path else 'repo'
        self.repoUrl = repoUrl
        self.repo = None
        self.compatSets = compatSets
        self.diffProcessor = diffProcessor
        try:
            self.repo = Repo(self.path)
            self._info('Repo found at "%s".  Pulling from remote...' % (self.path))
            self.repo.remote().pull()
            self._info('done pulling')
        except NoSuchPathError:
            self._info('%s does not exist.  Cloning from %s' % (self.path, self.repoUrl))
            self.repo = Repo.clone_from(self.repoUrl, self.path)
        except InvalidGitRepositoryError:
            self._warn('%s exists, but is not a git repo.  Remove the directory, or specify a different one.' % self.path)
    def _error(self, string):
        print('E: ' + str(string), file=sys.stderr)
    def _warn(self, string):
        print('W: ' + str(string), file=sys.stderr)
    def _info(self, string):
        print('I: ' + str(string), file=sys.stderr)
    def _checkVersionMatches(self, version, conditions=[]):
        #TODO: validate conditions first
        for condition in conditions:
            try:
                if not semver.match(version, condition):
                    return False
            except ValueError as e:
                self._warn('skipping tag %s: %s' % (version, e))
                return False
        return True
    def getTagsMatching(self, conditions=[]):
        return filter(lambda tag: self._checkVersionMatches(tag.name, conditions), self.repo.tags)
    def getTagPairs(self, conditions=[]):
        tagsToConsider = self.getTagsMatching(conditions)
        return itertools.combinations(tagsToConsider, 2)
    def getCompatiblePairs(self):
        for compatSet in self.compatSets:
            for pair in self.getTagPairs(compatSet):
                if semver.compare(pair[0].name, pair[1].name) > 0:
                    pair = (pair[1], pair[0])  # Always compare older->newer
                self._info('Processing version pair: %s->%s' % (pair[0].name, pair[1].name))
                yield pair
    def _getPatchFromDiff(self, diff):
        patch = ''
        a_path = self.diffProcessor.processPath(diff.a_path) if self.diffProcessor else diff.a_path
        b_path = self.diffProcessor.processPath(diff.b_path) if self.diffProcessor else diff.b_path
        a_path = ("a/%s" % a_path) if a_path else '/dev/null'
        b_path = ("b/%s" % b_path) if b_path else '/dev/null'
        patch = patch + "--- %s\n" % (a_path)
        patch = patch + "+++ %s\n" % (b_path)
        patch = patch + diff.diff.decode('UTF-8')
        patch = patch + "\n"
        tags = self.diffProcessor.tag(diff) if self.diffProcessor else ()
        return tags, patch
    def _getPatchesFromDiffIndex(self, diffIndex):
        for diff in diffIndex:
            try:
                yield self._getPatchFromDiff(diff)
            except Exception as e:
                self._warn('Skipping patch: %s' % (e))
                yield None, None
    def _getDiffIndexFromPair(self, pair):
            return pair[0].commit.diff(pair[1].commit, create_patch=True)
    def compute(self):
        for pair in self.getCompatiblePairs():
            for patch in self._getPatchesFromDiffIndex(self._getDiffIndexFromPair(pair)):
                yield (pair,) + patch

class _PatchRange:
    def __init__(self, compatSets=[], diffProcessor=None, rangeTags=()):
        self.compatSets = compatSets
        self.diffProcessor = diffProcessor
        self.rangeTags = rangeTags

if __name__ == "__main__":
    REPO='https://github.com/amzn/amazon-payments-magento-2-plugin.git'
    PATCHDIR='patches'

    patchRanges = [
        _PatchRange([['>=2.1.0', '<3.0.0']], ModuleDiffProcessor([
            ModuleGroup('amzn/amazon-pay-and-login-with-amazon-core-module', 'src/Core'),
            ModuleGroup('amzn/amazon-pay-module', 'src/Payment'),
            ModuleGroup('amzn/login-with-amazon-module', 'src/Login')
          ]), ('Magento2.2',)),
        _PatchRange([['>=3.0.0', '<4.0.0']], ModuleDiffProcessor([
            ModuleGroup('amzn/amazon-pay-and-login-with-amazon-core-module', 'src/Core'),
            ModuleGroup('amzn/amazon-pay-module', 'src/Payment'),
            ModuleGroup('amzn/login-with-amazon-module', 'src/Login')
          ]), ('Magento2.3',)),
        _PatchRange([['>=4.0.0', '<5.0.0']], ModuleDiffProcessor([
            ModuleGroup('amzn/amazon-pay-and-login-with-amazon-core-module', 'src/Core'),
            ModuleGroup('amzn/amazon-pay-module', 'src/Payment'),
            ModuleGroup('amzn/login-with-amazon-module', 'src/Login')
          ]), ('Magento2.4',)),
#        _PatchRange([['>=3.1.0','<=4.0.0']], None, ('Magento2.3','amzn/amazon-pay-and-login-magento-2-module'))
    ]

    matrix = PatchMatrix(REPO)

    for patchRange in patchRanges:
        matrix.compatSets = patchRange.compatSets
        matrix.diffProcessor = patchRange.diffProcessor
        patchesToWrite = {}
        for pair, tags, patch in matrix.compute():
            if not patch:
                continue
            path = PATCHDIR.rstrip('/') + '/'
            tags = patchRange.rangeTags + tags
            if tags:
                path = path + '/'.join(tags) + '/'
            filename = '%s%s-%s.patch' % (path, pair[0].name, pair[1].name)
            if filename in patchesToWrite:
                patchesToWrite[filename]['patch'] = patchesToWrite[filename]['patch'] + patch
            else:
                patchesToWrite[filename] = {'path': path, 'patch': patch}
        for filename, patch in patchesToWrite.items():
            if not os.path.exists(patch['path']):
                os.makedirs(patch['path'], exist_ok=True)
            print('Writing patch to %s' % (filename))
            out = open(filename, 'w')
            out.write(patch['patch'])
            out.close()

