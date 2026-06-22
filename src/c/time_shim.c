#define _GNU_SOURCE
#include <dlfcn.h>
#include <time.h>
#include <sys/time.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

typedef int (*gettimeofday_t)(struct timeval *, struct timezone *);
typedef time_t (*time_t)(time_t *);
typedef int (*clock_gettime_t)(clockid_t, struct timespec *);

static gettimeofday_t real_gettimeofday = NULL;
static time_t real_time = NULL;
static clock_gettime_t real_clock_gettime = NULL;

static long long offset_sec = 0;
static long long offset_nsec = 0;
static int initialized = 0;
static pthread_mutex_t init_mutex = PTHREAD_MUTEX_INITIALIZER;

/**
 * 规范化 timeval 结构体
 *
 * 确保 tv_usec 在 [0, 1000000) 范围内
 * 使用 while 循环处理任意次数的进位/借位
 *
 * 注意: 即使 Python 端正确传递了规范化的偏移量，
 * 这里仍然需要健壮的规范化逻辑，因为:
 * 1. offset_nsec / 1000 可能产生超过 1 秒的微秒数
 * 2. C 语言负数除法是截断取整，可能导致边界问题
 * 3. 防止未来的代码变更引入异常
 */
static inline void normalize_timeval(struct timeval *tv) {
    while (tv->tv_usec >= 1000000) {
        tv->tv_sec += 1;
        tv->tv_usec -= 1000000;
    }
    while (tv->tv_usec < 0) {
        tv->tv_sec -= 1;
        tv->tv_usec += 1000000;
    }
}

/**
 * 规范化 timespec 结构体
 *
 * 确保 tv_nsec 在 [0, 1000000000) 范围内
 * 使用 while 循环处理任意次数的进位/借位
 */
static inline void normalize_timespec(struct timespec *tp) {
    while (tp->tv_nsec >= 1000000000) {
        tp->tv_sec += 1;
        tp->tv_nsec -= 1000000000;
    }
    while (tp->tv_nsec < 0) {
        tp->tv_sec -= 1;
        tp->tv_nsec += 1000000000;
    }
}

static void time_shim_init(void) {
    if (initialized) return;

    pthread_mutex_lock(&init_mutex);
    if (initialized) {
        pthread_mutex_unlock(&init_mutex);
        return;
    }

    const char *enabled = getenv("TIME_TRAVEL_ENABLED");
    if (enabled && strcmp(enabled, "1") == 0) {
        const char *off_sec = getenv("TIME_TRAVEL_OFFSET_SEC");
        const char *off_nsec = getenv("TIME_TRAVEL_OFFSET_NSEC");

        if (off_sec) {
            offset_sec = atoll(off_sec);
        }
        if (off_nsec) {
            offset_nsec = atoll(off_nsec);
        }
    }

    real_gettimeofday = (gettimeofday_t)dlsym(RTLD_NEXT, "gettimeofday");
    real_time = (time_t)dlsym(RTLD_NEXT, "time");
    real_clock_gettime = (clock_gettime_t)dlsym(RTLD_NEXT, "clock_gettime");

    initialized = 1;
    pthread_mutex_unlock(&init_mutex);
}

/**
 * 劫持 gettimeofday 系统调用
 *
 * Bug 修复:
 * 原代码只使用单次 if-else 处理进位/借位，
 * 当 offset_nsec 很大时（比如穿越回多年前），
 * tv_usec 可能产生多次溢出，单次修正无法将其
 * 调整到合法范围 [0, 1000000)，导致返回非法的
 * timeval 结构体，造成目标进程崩溃或行为异常。
 *
 * 修复方案:
 * 使用 while 循环确保完全规范化，无论偏移量多大，
 * 都能保证 tv_usec 在合法范围内。
 */
int gettimeofday(struct timeval *tv, struct timezone *tz) {
    time_shim_init();

    int ret = real_gettimeofday(tv, tz);
    if (ret == 0 && tv) {
        tv->tv_sec += offset_sec;
        tv->tv_usec += (offset_nsec / 1000);

        normalize_timeval(tv);
    }
    return ret;
}

time_t time(time_t *t) {
    time_shim_init();

    time_t ret = real_time(t);
    ret += offset_sec;

    if (t) {
        *t = ret;
    }
    return ret;
}

/**
 * 劫持 clock_gettime 系统调用
 *
 * 同样的 Bug 修复: 使用 while 循环确保 tv_nsec
 * 完全规范化到 [0, 1000000000) 范围内。
 */
int clock_gettime(clockid_t clk_id, struct timespec *tp) {
    time_shim_init();

    int ret = real_clock_gettime(clk_id, tp);
    if (ret == 0 && tp) {
        if (clk_id == CLOCK_REALTIME ||
            clk_id == CLOCK_REALTIME_COARSE ||
            clk_id == CLOCK_REALTIME_ALARM ||
            clk_id == CLOCK_BOOTTIME_ALARM) {
            tp->tv_sec += offset_sec;
            tp->tv_nsec += offset_nsec;

            normalize_timespec(tp);
        }
    }
    return ret;
}
