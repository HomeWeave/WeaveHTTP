from distutils.command.clean import clean
from setuptools import setup, find_packages
from setuptools.command.install import install


class CleanInstall(install):
    def run(self):
        super(CleanInstall, self).run()
        c = clean(self.distribution)
        c.all = True
        c.finalize_options()
        c.run()


setup(
    name='dashboard',
    version='0.8',
    author='Srivatsan Iyer',
    author_email='supersaiyanmode.rox@gmail.com',
    packages=find_packages(),
    license='MIT',
    description='Dashboard for HomeWeave',
    install_requires=[
        'weavelib',
        'eventlet!=0.22',
        'bottle',
    ],
    cmdclass={'install': CleanInstall}
)
