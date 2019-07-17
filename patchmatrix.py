from git import Repo, NoSuchPathError, InvalidGitRepositoryError
import itertools
import semver
import sys
import os

class PatchMatrix:
    def __init__(self, repoUrl=None, compatSets=[], path=None):
        self.path = path if path else 'repo'
        self.repoUrl = repoUrl
        self.repo = None
        self.compatSets = compatSets
        try:
            self.repo = Repo(self.path)
            self._info('Repo found at %s.  Pulling from remote...' % (self.path))
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
                self._info(pair)
                yield pair
    def _getPatchFromDiff(self, diff):
        patch = ''
        a_path = ("a/%s" % diff.a_path) if diff.a_path else '/dev/null'
        b_path = ("b/%s" % diff.b_path) if diff.b_path else '/dev/null'
        patch = patch + "--- %s\n" % (a_path)
        patch = patch + "+++ %s\n" % (b_path)
        patch = patch + diff.diff.decode('UTF-8')
        patch = patch + "\n"
        return patch
    def _getPatchFromDiffIndex(self, diffIndex):
        patch = ''
        for diff in diffIndex:
             patch = patch + self._getPatchFromDiff(diff)
        return patch
    def _getDiffIndexFromPair(self, pair):
            return pair[0].commit.diff(pair[1].commit, create_patch=True)
    def _getPatchFromPair(self, pair):
        return self._getPatchFromDiffIndex(self._getDiffIndexFromPair(pair))
    def compute(self):
        for pair in self.getCompatiblePairs():
            yield (pair, self._getPatchFromPair(pair))


if __name__ == "__main__":
    REPO='https://github.com/BearGroup/amazon-payments-magento-2-plugin.git'
    COMPATSETS=[['>2.1.0','<2.2.0'],['>3.1.0','<4.0.0'],['>1.2.0','<1.3.0']]
#    COMPATSETS=[['>=1.0.0','<4.0.0']]
    PATCHDIR='patches'

    if not os.path.exists(PATCHDIR):
        os.makedirs(PATCHDIR)

    matrix = PatchMatrix(REPO, COMPATSETS)
    for pair, patch in matrix.compute():
        filename = '%s/%s-%s.patch' % (PATCHDIR, pair[0].name, pair[1].name)
        print('Writing patch to %s' % (filename))
        out = open(filename, 'w')
        out.write(patch)
        out.close()

