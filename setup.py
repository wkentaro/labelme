from distutils.command.build_py import build_py as BuildPyCommand
from distutils.spawn import find_executable
import os.path as osp
from setuptools import find_packages
from setuptools import setup
import shlex
import subprocess
import sys


version = '2.6.2'


try:
    import PyQt5  # NOQA
    PYQT_VERSION = 5
except ImportError:
    try:
        import PyQt4  # NOQA
        PYQT_VERSION = 4
    except ImportError:
        sys.stderr.write('Please install PyQt4 or PyQt5.\n')
        sys.exit(1)


if sys.argv[1] == 'release':
    commands = [
        'git tag v{:s}'.format(version),
        'git push origin master --tag',
        'python setup.py sdist',
        'twine upload dist/labelme-{:s}.tar.gz'.format(version),
    ]
    sys.exit(sum(subprocess.call(shlex.split(cmd)) for cmd in commands))


here = osp.dirname(osp.abspath(__file__))


class LabelmeBuildPyCommand(BuildPyCommand):

    def run(self):
        pyrcc = 'pyrcc{:d}'.format(PYQT_VERSION)
        if find_executable(pyrcc) is None:
            sys.stderr.write('Please install {:s} command.\n'.format(pyrcc))
            sys.stderr.write('(See https://github.com/wkentaro/labelme.git)\n')
            sys.exit(1)
        package_dir = osp.join(here, 'labelme')
        src = 'resources.qrc'
        dst = 'resources.py'
        cmd = '{pyrcc} -o {dst} {src}'.format(pyrcc=pyrcc, src=src, dst=dst)
        print('+ {:s}'.format(cmd))
        subprocess.call(shlex.split(cmd), cwd=package_dir)
        BuildPyCommand.run(self)


setup(
    name='labelme',
    version=version,
    packages=find_packages(),
    cmdclass={'build_py': LabelmeBuildPyCommand},
    description='Annotation Tool for Object Segmentation.',
    long_description=open('README.md').read(),
    author='Kentaro Wada',
    author_email='www.kentaro.wada@gmail.com',
    url='https://github.com/wkentaro/labelme',
    install_requires=[
        'matplotlib',
        'Pillow>=2.8.0',
        'scipy',
        'scikit-image',
        'six',
        'PyYAML',
    ],
    license='GPLv3',
    keywords='Image Annotation, Machine Learning',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Topic :: Internet :: WWW/HTTP',
    ],
    package_data={'labelme': ['icons/*', 'resources.qrc']},
    entry_points={'console_scripts': ['labelme=labelme.app:main']},
    scripts=[
        'scripts/labelme_draw_json',
        'scripts/labelme_json_to_dataset',
        'scripts/labelme_on_docker',
    ],
)
