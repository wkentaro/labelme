from distutils.command.build_py import build_py as BuildPyCommand
from setuptools import find_packages
from setuptools import setup
import shlex
import subprocess
import sys


version = '1.0.1'


class LabelmeBuildPyCommand(BuildPyCommand):

    def run(self):
        BuildPyCommand.run(self)
        src = 'labelme/resources.py'
        dst = 'labelme/resources.qrc'
        cmd = 'pyrcc4 -o {0} {1}'.format(src, dst)
        print('converting {0} -> {1}'.format(src, dst))
        subprocess.check_call(shlex.split(cmd))


try:
    import PyQt4
except ImportError:
    sys.stderr.write('Please install PyQt4.\n')
    sys.exit(1)


setup(
    name='labelme',
    version=version,
    packages=find_packages(),
    cmdclass={'build_py': LabelmeBuildPyCommand},
    description='Simple Image Annotation Tool.',
    long_description=open('README.rst').read(),
    author='mpitid',
    author_email='mpitid@gmail.com',
    url='https://github.com/mpitid/pylabelme',
    install_requires=[],
    license='MIT',
    keywords='Image Annotation, Machine Learning',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Topic :: Internet :: WWW/HTTP',
    ],
    package_data={'labelme': ['icons']},
    scripts=['scripts/labelme'],
)
