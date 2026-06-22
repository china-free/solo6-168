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
typedef int (*getrusage_t)(int, struct rusage *);

static gettimeofday_t real_gettimeofday = NULL;
static time_t real_time = NULL;
static clock_gettime_t real_clock_gettime = NULL;

static long long offset_sec = 0;
static long long offset_nsec = 0;
static int initialized = 0;
static pthread_mutex_t init_mutex = PTHREAD_MUTEX_INITIALIZER;

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

int gettimeofday(struct timeval *tv, struct timezone *tz) {
    time_shim_init();

    int ret = real_gettimeofday(tv, tz);
    if (ret == 0 && tv) {
        tv->tv_sec += offset_sec;
        tv->tv_usec += (offset_nsec / 1000);
        if (tv->tv_usec >= 1000000) {
            tv->tv_sec += 1;
            tv->tv_usec -= 1000000;
        } else if (tv->tv_usec < 0) {
            tv->tv_sec -= 1;
            tv->tv_usec += 1000000;
        }
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
            if (tp->tv_nsec >= 1000000000) {
                tp->tv_sec += 1;
                tp->tv_nsec -= 1000000000;
            } else if (tp->tv_nsec < 0) {
                tp->tv_sec -= 1;
                tp->tv_nsec += 1000000000;
            }
        }
    }
    return ret;
}
