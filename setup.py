"""
Time Travel - 进程级时间穿梭模拟器
Python 包安装配置
"""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent
long_description = (here / "README.md").read_text(encoding="utf-8") if (here / "README.md").exists() else ""

setup(
    name="time-travel",
    version="1.0.0",
    description="进程级时间穿梭模拟器 - 利用 LD_PRELOAD 技术让目标进程看到自定义时间",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Time Travel Contributors",
    url="https://github.com/time-travel/time-travel",
    package_dir={"": "src/python"},
    packages=find_packages(where="src/python"),
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pylint>=2.15",
        ],
    },
    entry_points={
        "console_scripts": [
            "time-travel=time_travel.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Systems Administration",
    ],
    keywords="time testing ldpreload syscall-hijack debugging",
)
