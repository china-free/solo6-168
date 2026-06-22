"""
包内资源目录

存放编译后的 C 共享库文件:
- time_shim.so (Linux)
- time_shim.dylib (macOS)

Makefile 会将编译好的共享库复制到这里，
setup.py 会将这个目录的文件打包进 wheel。
"""
