cmake_minimum_required(VERSION 3.20)
project(audio_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bin)

add_executable(audio_engine src/main.cpp)

target_link_libraries(audio_engine PRIVATE ws2_32)
