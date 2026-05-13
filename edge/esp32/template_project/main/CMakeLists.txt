if(DEFINED ENABLE_TRACES)
    add_compile_definitions(ENABLE_TRACES)
endif()
idf_component_register(
    SRCS
    "events_mgr.c"
    "main.c"
    "data_reader.c"
    "models_mgr.c"
    "${CMAKE_BINARY_DIR}/build_generated/models_data.c"
    "scheduler.c"
    "predictions_mgr.c"
    "tflite_runner.cpp"
    "trace.c"
   
    INCLUDE_DIRS
        "."
        "${CMAKE_BINARY_DIR}"
        "${CMAKE_BINARY_DIR}/build_generated"
    REQUIRES
        freertos
        driver
        esp_driver_uart
        #tflite_runner
        esp-tflite-micro
        esp_timer
)
