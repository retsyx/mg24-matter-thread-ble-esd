cmake_minimum_required(VERSION 3.25)
project(MailboxMotion VERSION 1.0 LANGUAGES C CXX ASM)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 99)
option(MAILBOX_CONSOLE_KEEP_AWAKE "Enable USB UART, shell and awake debugging" OFF)
option(MAILBOX_BATTERY_INSTALLED "Report a fitted LiPo battery" OFF)
option(MAILBOX_RADIO_GATED_SWITCH "Gate the antenna switch supply with radio activity" ON)
foreach(path SDK_PATH MATTER_PATH)
  if(NOT IS_DIRECTORY "${${path}}")
    message(FATAL_ERROR "Set ${path} to the installed Silicon Labs package; scripts/build.py discovers it.")
  endif()
endforeach()
include(platform_codegen.cmake)
include(MailboxMotion.cmake)
# Only the board initialization uses this option. Keep SDK and
# protocol sources independent of it so A/B builds recompile only this file.
set_property(SOURCE "../src/main.cpp" APPEND PROPERTY COMPILE_DEFINITIONS
  "MAILBOX_RADIO_GATED_SWITCH=$<BOOL:${MAILBOX_RADIO_GATED_SWITCH}>")
add_dependencies(slc platform_codegen)
add_executable(MailboxMotion)
set_property(TARGET MailboxMotion APPEND PROPERTY LINK_DEPENDS
  "${PLATFORM_GENERATED_DIR}/linkerfile.ld")
target_link_libraries(MailboxMotion PRIVATE slc)
set_target_properties(MailboxMotion PROPERTIES LINKER_LANGUAGE C)
add_custom_command(TARGET MailboxMotion POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:MailboxMotion> $<TARGET_FILE_DIR:MailboxMotion>/MailboxMotion.hex
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:MailboxMotion> $<TARGET_FILE_DIR:MailboxMotion>/MailboxMotion.bin
  COMMAND ${CMAKE_SIZE_UTIL} $<TARGET_FILE:MailboxMotion>)
