# Time Travel - 进程级时间穿梭模拟器 Makefile
#
# 主要目标:
#   make            - 编译 C 劫持共享库
#   make install    - 安装到系统（可选）
#   make clean      - 清理编译产物
#   make test       - 运行测试
#   make lint       - 代码质量检查

# 编译器和编译选项
CC = gcc
CFLAGS = -Wall -Wextra -fPIC -O2 -D_GNU_SOURCE
LDFLAGS = -shared -ldl -lpthread

# 目录
SRC_DIR = src
C_DIR = $(SRC_DIR)/c
PYTHON_DIR = $(SRC_DIR)/python
LIB_DIR = lib
BIN_DIR = bin
TEST_DIR = tests

# 源文件和目标文件
C_SRC = $(C_DIR)/time_shim.c
SHARED_LIB = $(LIB_DIR)/time_shim.so

# Python 可执行脚本
CLI_SCRIPT = $(BIN_DIR)/time-travel
CLI_SOURCE = $(PYTHON_DIR)/bin/time-travel

# 默认目标
.PHONY: all
all: build

# 构建共享库
.PHONY: build
build: $(SHARED_LIB) $(CLI_SCRIPT)

# 编译 C 共享库
$(SHARED_LIB): $(C_SRC) | $(LIB_DIR)
	@echo "编译时间劫持共享库..."
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<
	@echo "完成: $@"

# 创建 lib 目录
$(LIB_DIR):
	@mkdir -p $(LIB_DIR)

# 创建 bin 目录
$(BIN_DIR):
	@mkdir -p $(BIN_DIR)

# 创建可执行脚本
$(CLI_SCRIPT): $(CLI_SOURCE) | $(BIN_DIR)
	@echo "创建 CLI 可执行脚本..."
	@cp $(CLI_SOURCE) $(CLI_SCRIPT)
	@chmod +x $(CLI_SCRIPT)
	@echo "完成: $@"

# 安装到系统
.PHONY: install
install: build
	@echo "安装 Time Travel 工具..."
	@install -m 755 $(SHARED_LIB) /usr/local/lib/
	@install -m 755 $(CLI_SCRIPT) /usr/local/bin/time-travel
	@ldconfig
	@echo "安装完成。可使用 'time-travel' 命令。"

# 卸载
.PHONY: uninstall
uninstall:
	@echo "卸载 Time Travel 工具..."
	@rm -f /usr/local/lib/time_shim.so
	@rm -f /usr/local/bin/time-travel
	@ldconfig
	@echo "卸载完成。"

# 运行测试
.PHONY: test
test: build
	@echo "运行测试..."
	@cd $(TEST_DIR) && python3 -m pytest -v

# 代码质量检查
.PHONY: lint
lint:
	@echo "检查 Python 代码质量..."
	@cd $(PYTHON_DIR) && python3 -m pylint time_travel/ --disable=C0114,C0115,C0116
	@echo "检查 C 代码..."
	@$(CC) -Wall -Wextra -fsyntax-only $(C_SRC)

# 清理
.PHONY: clean
clean:
	@echo "清理编译产物..."
	@rm -rf $(LIB_DIR)
	@rm -rf $(BIN_DIR)
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name ".pytest_cache" -delete
	@echo "清理完成。"

# 帮助信息
.PHONY: help
help:
	@echo "Time Travel - 进程级时间穿梭模拟器"
	@echo ""
	@echo "可用目标:"
	@echo "  make          - 编译 C 劫持共享库（默认）"
	@echo "  make build    - 同 make"
	@echo "  make install  - 安装到系统 (/usr/local)"
	@echo "  make uninstall - 从系统卸载"
	@echo "  make test     - 运行测试套件"
	@echo "  make lint     - 代码质量检查"
	@echo "  make clean    - 清理所有编译产物"
	@echo ""
	@echo "使用示例:"
	@echo "  make"
	@echo "  ./bin/time-travel --date \"2025-12-31\" -- date"
