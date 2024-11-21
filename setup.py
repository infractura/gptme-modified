from setuptools import setup, find_packages

setup(
    name='gpt-modified',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'click',
        'rich',
        'anthropic',
        'openai',
        'python-dotenv',
    ],
    entry_points={
        'console_scripts': [
            'gptme=gptme.cli:main',
        ],
    },
)

