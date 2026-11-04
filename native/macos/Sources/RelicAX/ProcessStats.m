#import "RelicAX.h"
#include <libproc.h>
#include <unistd.h>

NSDictionary<NSString *, NSNumber *> *RelicProcessStats(void) {
    struct proc_taskinfo info = {0};
    int result = proc_pidinfo(getpid(), PROC_PIDTASKINFO, 0, &info, sizeof(info));
    return @{@"valid": @(result == sizeof(info)), @"resident_bytes": @(info.pti_resident_size),
             @"threads": @(info.pti_threadnum),
             @"cpu_seconds": @((info.pti_total_user + info.pti_total_system) / 1e9)};
}
