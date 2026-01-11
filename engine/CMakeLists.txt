cmake_minimum_required(VERSION 3.10)
project(audio_engine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Windows-specific
if(WIN32)
    add_definitions(-DWIN32_LEAN_AND_MEAN)
    add_definitions(-DNOMINMAX)
endif()

# Source files
set(SOURCES
    src/main.cpp
    # src/audio_capture.cpp
    # src/proof_mode.cpp
)

# Executable
add_executable(audio_engine ${SOURCES})

# Windows libraries
if(WIN32)
    target_link_libraries(audio_engine
        ws2_32      # Windows Sockets
        # winmm      # Windows Multimedia (for WASAPI)
    )
endif()

# Install
install(TARGETS audio_engine RUNTIME DESTINATION bin)
