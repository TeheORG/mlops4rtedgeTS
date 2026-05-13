#ifndef PREDICTIONS_MGR_H
#define PREDICTIONS_MGR_H

#include <stddef.h>
#include "events_mgr.h"
#include "scheduler.h"
#include "config.h"
#include "trace.h"


void prediction_mgr_init(events_mgr_t *evt_mgr);
void prediction_mgr_start(const schedule_entry_t *entries,
                          size_t count);
#endif


