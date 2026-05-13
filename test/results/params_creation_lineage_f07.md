# Tabla por Parametro: Creacion y Linajes que lo Usan

Fase hoja analizada: f07_modval
Filtro de variantes hoja: `^v70[0-9]$`

Agrupacion: mismo parametro + misma variante de creacion + mismo valor de creacion.
Vista de prueba: 3 columnas (fase-crea, param, detalle multilinea).

Filas base: 106
Filas agrupadas para visualizacion: 18

| fase-crea | param | detalle (variant-crea | value | linaje) |
| --- | --- | --- |
| f01_explore | Tu | v100 \| 10 \| v700, v701, v702, v703, v704, v705, v706, v707, v708 |
| f03_windows | LT | v300 \| 1 \| v700, v701, v702, v703, v704, v705, v706, v707, v708 |
| f03_windows | OW | v300 \| 6 \| v700, v701, v702, v703, v704, v705, v706, v707, v708 |
| f03_windows | PW | v300 \| 1 \| v700, v701, v702, v703, v704, v705, v706, v707, v708 |
| f03_windows | event_type_count | v300 \| 221 \| v700, v701, v702, v703, v704, v705, v706, v707, v708 |
| f04_targets | prediction_name | v400 \| Battery_Active_Power_any-to-80_100 \| v700<br>v401 \| Battery_Active_Power_Set_Response_any-to-80_100 \| v701<br>v402 \| PVPCS_Active_Power_any-to-80_100 \| v702<br>v403 \| GE_Active_Power_any-to-80_100 \| v703<br>v404 \| GE_Body_Active_Power_any-to-80_100 \| v704<br>v405 \| GE_Body_Active_Power_Set_Response_any-to-80_100 \| v705<br>v406 \| FC_Active_Power_FC_END_Set_any-to-80_100 \| v706<br>v407 \| FC_Active_Power_any-to-80_100 \| v707<br>v408 \| MG-LV-MSB_AC_Voltage_any-to-80_100 \| v708 |
| f05_modeling | best_precision | v500 \| 1.0000 \| v700<br>v501 \| 0.2727 \| v701<br>v502 \| 0.7847 \| v702<br>v503 \| 0.8956 \| v703<br>v504 \| 0.7692 \| v704<br>v506 \| 0.0000 \| v706<br>v507 \| 0.6154 \| v707 |
| f05_modeling | best_recall | v500 \| 0.2727 \| v700<br>v501 \| 0.0714 \| v701<br>v502 \| 0.5793 \| v702<br>v503 \| 0.9216 \| v703<br>v504 \| 0.6071 \| v704<br>v506 \| 0.0000 \| v706<br>v507 \| 0.1667 \| v707 |
| f05_modeling | decision_threshold | v500 \| 0.1142 \| v700<br>v501 \| 0.5541 \| v701<br>v502 \| 0.4022 \| v702<br>v503 \| 0.6958 \| v703<br>v504 \| 0.6170 \| v704<br>v506 \| 0.0008 \| v706<br>v507 \| 0.6342 \| v707 |
| f05_modeling | model_family | v500 \| cnn1d \| v700<br>v501 \| cnn1d \| v701<br>v502 \| cnn1d \| v702<br>v503 \| cnn1d \| v703<br>v504 \| cnn1d \| v704<br>v505 \| cnn1d \| v705<br>v506 \| cnn1d \| v706<br>v507 \| cnn1d \| v707<br>v508 \| cnn1d \| v708 |
| f05_modeling | trainable | v500 \| true \| v700<br>v501 \| true \| v701<br>v502 \| true \| v702<br>v503 \| true \| v703<br>v504 \| true \| v704<br>v505 \| false \| v705<br>v506 \| true \| v706<br>v507 \| true \| v707<br>v508 \| false \| v708 |
| f06_quant | arena_estimada_bytes | v600 \| 120840 \| v700<br>v601 \| 90816 \| v701<br>v602 \| 75900 \| v702<br>v603 \| 90816 \| v703<br>v604 \| 90816 \| v704<br>v606 \| 90816 \| v706<br>v607 \| 90816 \| v707 |
| f06_quant | edge_capable | v600 \| true \| v700<br>v601 \| true \| v701<br>v602 \| true \| v702<br>v603 \| true \| v703<br>v604 \| true \| v704<br>v605 \| false \| v705<br>v606 \| true \| v706<br>v607 \| true \| v707<br>v608 \| false \| v708 |
| f06_quant | footprint_estimated_bytes | v600 \| 201400 \| v700<br>v601 \| 151360 \| v701<br>v602 \| 126500 \| v702<br>v603 \| 151360 \| v703<br>v604 \| 151360 \| v704<br>v606 \| 151360 \| v706<br>v607 \| 151360 \| v707 |
| f06_quant | model_size_bytes | v600 \| 80560 \| v700<br>v601 \| 60544 \| v701<br>v602 \| 50600 \| v702<br>v603 \| 60544 \| v703<br>v604 \| 60544 \| v704<br>v606 \| 60544 \| v706<br>v607 \| 60544 \| v707 |
| f06_quant | operators | v600 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v700<br>v601 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v701<br>v602 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v702<br>v603 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v703<br>v604 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v704<br>v606 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v706<br>v607 \| ["CAST", "CONV_2D", "DEQUANTIZE", "EXPAND_DIMS", "FULLY_CONNECTED", "GATHER", "LOGISTIC", "REDUCE_MAX", "RESHAPE"] \| v707 |
| f07_modval | itmax_ms | v700 \| 100 \| v700<br>v701 \| 100 \| v701<br>v702 \| 100 \| v702<br>v703 \| 100 \| v703<br>v704 \| 100 \| v704<br>v705 \| 100 \| v705<br>v706 \| 100 \| v706<br>v707 \| 100 \| v707<br>v708 \| 100 \| v708 |
| f07_modval | quality_score | v700 \| null \| v700<br>v701 \| null \| v701<br>v702 \| null \| v702<br>v703 \| null \| v703<br>v704 \| null \| v704<br>v706 \| null \| v706<br>v707 \| null \| v707 |
