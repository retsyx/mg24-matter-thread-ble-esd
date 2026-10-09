# Generate SDK glue and the Matter data model from maintained project inputs.
foreach(path SILABS_PYTHON_PATH GCC_PATH ZAP_PATH)
  if(NOT IS_DIRECTORY "${${path}}")
    message(FATAL_ERROR "Set ${path} to its installed package; scripts/build.py discovers it.")
  endif()
endforeach()
foreach(tool SLC_CLI JAVA_EXECUTABLE SILABS_PYTHON_EXECUTABLE GCC_EXECUTABLE ZAP_CLI)
  if(NOT EXISTS "${${tool}}" OR IS_DIRECTORY "${${tool}}")
    message(FATAL_ERROR "Set ${tool} to its installed executable; scripts/build.py discovers it with SLT.")
  endif()
endforeach()

set(PLATFORM_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/slc/autogen")
set(MATTER_GENERATED_DIR "${PLATFORM_GENERATED_DIR}/zap-generated")
set(CODEGEN_STAMP "${PLATFORM_GENERATED_DIR}/.generation.stamp")
set(PROJECT_INPUT_DIR "${CMAKE_CURRENT_LIST_DIR}/..")
set(MATTER_ZAP_TEMPLATES "${MATTER_PATH}/src/app/zap-templates")

set(PLATFORM_GENERATED_FILES)
foreach(name
  RTE_Components.h gatt_db.c gatt_db.h gen.properties linkerfile.ld
  sl_application_type.h sl_bluetooth.c sl_bluetooth.h sl_component_catalog.h
  sl_event_handler.c sl_event_handler.h sl_iostream_handles.c
  sl_iostream_handles.h sl_iostream_init_instances.h sl_ot_custom_cli.c
  sl_ot_init.c sl_ot_init.h sl_simple_led_instances.c sl_simple_led_instances.h
  sl_uartdrv_init.c sl_uartdrv_instances.h sli_mbedtls_config_autogen.h
  sli_mbedtls_config_transform_autogen.h sli_psa_builtin_config_autogen.h
  sli_psa_config_autogen.h
)
  list(APPEND PLATFORM_GENERATED_FILES "${PLATFORM_GENERATED_DIR}/${name}")
endforeach()

set(MATTER_GENERATED_SOURCES
  "${MATTER_GENERATED_DIR}/app/callback-stub.cpp"
  "${MATTER_GENERATED_DIR}/app/cluster-init-callback.cpp"
  "${MATTER_GENERATED_DIR}/attributes/Accessors.cpp"
  "${MATTER_GENERATED_DIR}/cluster-objects.cpp"
  "${MATTER_GENERATED_DIR}/IMClusterCommandHandler.cpp"
)

# Register fixed headers alongside compiled sources. Per-cluster headers are
# created by the same step; --generate also restores selectively removed files.
file(READ "${MATTER_ZAP_TEMPLATES}/app-templates.json" MATTER_TEMPLATE_MANIFEST)
string(JSON MATTER_TEMPLATE_COUNT LENGTH "${MATTER_TEMPLATE_MANIFEST}" templates)
math(EXPR MATTER_TEMPLATE_LAST "${MATTER_TEMPLATE_COUNT} - 1")
set(MATTER_GENERATED_HEADERS)
foreach(index RANGE ${MATTER_TEMPLATE_LAST})
  string(JSON output GET "${MATTER_TEMPLATE_MANIFEST}" templates ${index} output)
  if(output MATCHES "\\.(h|ipp)$" AND NOT output MATCHES "\\{")
    list(APPEND MATTER_GENERATED_HEADERS "${MATTER_GENERATED_DIR}/${output}")
  endif()
endforeach()

file(GLOB_RECURSE PROJECT_CODEGEN_CONFIG CONFIGURE_DEPENDS
  "${PROJECT_INPUT_DIR}/config/*.h"
  "${PROJECT_INPUT_DIR}/config/*.btconf"
  "${PROJECT_INPUT_DIR}/config/*.mattpconf"
  "${PROJECT_INPUT_DIR}/config/*.prioconf"
  "${PROJECT_INPUT_DIR}/config/*.zap"
)
file(GLOB_RECURSE SDK_CODEGEN_INPUTS CONFIGURE_DEPENDS
  "${SDK_PATH}/*.slcc" "${SDK_PATH}/*.jinja"
  "${MATTER_PATH}/slc/*.slcc" "${MATTER_PATH}/slc/*.jinja"
  "${MATTER_ZAP_TEMPLATES}/*"
  "${MATTER_PATH}/third_party/matter_sdk/src/app/zap-templates/*"
  "${MATTER_PATH}/third_party/matter_sdk/src/app/common/templates/*"
  "${SDK_PATH}/protocol/bluetooth/bin/gatt/*.py"
)

add_custom_command(
  OUTPUT "${CODEGEN_STAMP}" ${PLATFORM_GENERATED_FILES} ${MATTER_GENERATED_SOURCES}
  BYPRODUCTS ${MATTER_GENERATED_HEADERS}
  COMMAND "${SILABS_PYTHON_EXECUTABLE}" -B
    "${PROJECT_INPUT_DIR}/scripts/generate-platform.py"
    --slc "${SLC_CLI}" --java "${JAVA_EXECUTABLE}"
    --python "${SILABS_PYTHON_PATH}" --python-executable "${SILABS_PYTHON_EXECUTABLE}"
    --sdk "${SDK_PATH}" --matter "${MATTER_PATH}" --gcc "${GCC_PATH}"
    --gcc-executable "${GCC_EXECUTABLE}" --zap "${ZAP_PATH}" --zap-cli "${ZAP_CLI}"
    --project "${PROJECT_INPUT_DIR}/MailboxMotion.slcp"
    --output "${CMAKE_CURRENT_BINARY_DIR}/slc"
  COMMAND "${CMAKE_COMMAND}" -E touch "${CODEGEN_STAMP}"
  DEPENDS "${PROJECT_INPUT_DIR}/MailboxMotion.slcp"
    "${PROJECT_INPUT_DIR}/scripts/generate-platform.py"
    "${SLC_CLI}" "${JAVA_EXECUTABLE}" "${SILABS_PYTHON_EXECUTABLE}"
    "${ZAP_CLI}" ${PROJECT_CODEGEN_CONFIG} ${SDK_CODEGEN_INPUTS}
  COMMENT "Generating Silicon Labs platform and Matter data model"
  VERBATIM
)
add_custom_target(platform_codegen
  DEPENDS "${CODEGEN_STAMP}" ${PLATFORM_GENERATED_FILES} ${MATTER_GENERATED_SOURCES}
)
