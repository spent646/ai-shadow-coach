#include <winsock2.h>
#include <ws2tcpip.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#pragma comment(lib, "Ws2_32.lib")

namespace {
constexpr int kSampleRate = 48000;
constexpr int kFrameSamples = 960;
constexpr int kFrameBytes = kFrameSamples * sizeof(int16_t);
constexpr double kTwoPi = 6.283185307179586476925286766559;

std::atomic<bool> g_running{true};

void log_info(const std::string &msg) {
    std::cout << "[audio_engine] " << msg << std::endl;
}

void log_error(const std::string &msg) {
    std::cerr << "[audio_engine] " << msg << std::endl;
}

BOOL WINAPI console_handler(DWORD ctrl_type) {
    if (ctrl_type == CTRL_C_EVENT || ctrl_type == CTRL_BREAK_EVENT || ctrl_type == CTRL_CLOSE_EVENT) {
        g_running.store(false);
        return TRUE;
    }
    return FALSE;
}

struct StreamConfig {
    std::string label;
    std::string host;
    int port = 0;
    double tone_hz = 220.0;
};

SOCKET create_listen_socket(const std::string &host, int port, const std::string &label) {
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    addrinfo *result = nullptr;
    std::string port_str = std::to_string(port);
    const char *host_ptr = host.empty() || host == "0.0.0.0" ? nullptr : host.c_str();

    int res = getaddrinfo(host_ptr, port_str.c_str(), &hints, &result);
    if (res != 0) {
        log_error(label + " getaddrinfo failed: " + std::to_string(res));
        return INVALID_SOCKET;
    }

    SOCKET listen_sock = INVALID_SOCKET;
    for (addrinfo *ptr = result; ptr != nullptr; ptr = ptr->ai_next) {
        listen_sock = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol);
        if (listen_sock == INVALID_SOCKET) {
            continue;
        }
        int opt = 1;
        setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<char *>(&opt), sizeof(opt));
        if (bind(listen_sock, ptr->ai_addr, static_cast<int>(ptr->ai_addrlen)) == SOCKET_ERROR) {
            closesocket(listen_sock);
            listen_sock = INVALID_SOCKET;
            continue;
        }
        if (listen(listen_sock, 1) == SOCKET_ERROR) {
            closesocket(listen_sock);
            listen_sock = INVALID_SOCKET;
            continue;
        }
        break;
    }

    freeaddrinfo(result);

    if (listen_sock == INVALID_SOCKET) {
        log_error(label + " failed to bind/listen on " + host + ":" + std::to_string(port));
    }

    return listen_sock;
}

bool send_all(SOCKET sock, const char *data, int len) {
    int total_sent = 0;
    while (total_sent < len) {
        int sent = send(sock, data + total_sent, len - total_sent, 0);
        if (sent == SOCKET_ERROR || sent == 0) {
            return false;
        }
        total_sent += sent;
    }
    return true;
}

void stream_worker(StreamConfig cfg) {
    SOCKET listen_sock = create_listen_socket(cfg.host, cfg.port, cfg.label);
    if (listen_sock == INVALID_SOCKET) {
        return;
    }

    log_info(cfg.label + " listening on " + cfg.host + ":" + std::to_string(cfg.port));

    std::vector<int16_t> frame(kFrameSamples, 0);
    double phase = 0.0;
    double phase_inc = kTwoPi * cfg.tone_hz / static_cast<double>(kSampleRate);

    while (g_running.load()) {
        sockaddr_in client_addr{};
        int addr_len = sizeof(client_addr);
        SOCKET client = accept(listen_sock, reinterpret_cast<sockaddr *>(&client_addr), &addr_len);
        if (client == INVALID_SOCKET) {
            if (g_running.load()) {
                log_error(cfg.label + " accept failed: " + std::to_string(WSAGetLastError()));
            }
            continue;
        }

        log_info(cfg.label + " client connected");
        auto next_time = std::chrono::steady_clock::now();

        while (g_running.load()) {
            for (int i = 0; i < kFrameSamples; ++i) {
                double sample = std::sin(phase);
                int16_t value = static_cast<int16_t>(sample * 10000.0);
                frame[i] = value;
                phase += phase_inc;
                if (phase >= kTwoPi) {
                    phase -= kTwoPi;
                }
            }

            if (!send_all(client, reinterpret_cast<const char *>(frame.data()), kFrameBytes)) {
                log_error(cfg.label + " send failed: " + std::to_string(WSAGetLastError()));
                break;
            }

            next_time += std::chrono::milliseconds(20);
            std::this_thread::sleep_until(next_time);
        }

        closesocket(client);
        log_info(cfg.label + " client disconnected");
    }

    closesocket(listen_sock);
}

void write_wav(const std::string &path, const std::vector<int16_t> &samples) {
    uint32_t data_bytes = static_cast<uint32_t>(samples.size() * sizeof(int16_t));
    uint32_t fmt_chunk_size = 16;
    uint16_t audio_format = 1;
    uint16_t num_channels = 1;
    uint32_t byte_rate = kSampleRate * num_channels * sizeof(int16_t);
    uint16_t block_align = num_channels * sizeof(int16_t);
    uint16_t bits_per_sample = 16;
    uint32_t riff_size = 4 + (8 + fmt_chunk_size) + (8 + data_bytes);

    std::ofstream out(path, std::ios::binary);
    if (!out) {
        log_error("failed to write " + path);
        return;
    }

    out.write("RIFF", 4);
    out.write(reinterpret_cast<const char *>(&riff_size), 4);
    out.write("WAVE", 4);

    out.write("fmt ", 4);
    out.write(reinterpret_cast<const char *>(&fmt_chunk_size), 4);
    out.write(reinterpret_cast<const char *>(&audio_format), 2);
    out.write(reinterpret_cast<const char *>(&num_channels), 2);
    out.write(reinterpret_cast<const char *>(&kSampleRate), 4);
    out.write(reinterpret_cast<const char *>(&byte_rate), 4);
    out.write(reinterpret_cast<const char *>(&block_align), 2);
    out.write(reinterpret_cast<const char *>(&bits_per_sample), 2);

    out.write("data", 4);
    out.write(reinterpret_cast<const char *>(&data_bytes), 4);
    out.write(reinterpret_cast<const char *>(samples.data()), data_bytes);
}

void run_proof(int seconds) {
    int total_samples = seconds * kSampleRate;
    std::vector<int16_t> mic_samples(total_samples, 0);
    std::vector<int16_t> loop_samples(total_samples, 0);

    double mic_phase = 0.0;
    double loop_phase = 0.0;
    double mic_inc = kTwoPi * 440.0 / static_cast<double>(kSampleRate);
    double loop_inc = kTwoPi * 220.0 / static_cast<double>(kSampleRate);

    for (int i = 0; i < total_samples; ++i) {
        mic_samples[i] = static_cast<int16_t>(std::sin(mic_phase) * 10000.0);
        loop_samples[i] = static_cast<int16_t>(std::sin(loop_phase) * 10000.0);
        mic_phase += mic_inc;
        loop_phase += loop_inc;
        if (mic_phase >= kTwoPi) {
            mic_phase -= kTwoPi;
        }
        if (loop_phase >= kTwoPi) {
            loop_phase -= kTwoPi;
        }
    }

    write_wav("mic.wav", mic_samples);
    write_wav("loop.wav", loop_samples);
    log_info("proof mode wrote mic.wav and loop.wav");
}

struct Args {
    std::string host = "127.0.0.1";
    int mic_port = 0;
    int loop_port = 0;
    bool proof = false;
    int seconds = 10;
};

bool parse_args(int argc, char **argv, Args &out) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--host" && i + 1 < argc) {
            out.host = argv[++i];
        } else if (arg == "--mic-port" && i + 1 < argc) {
            out.mic_port = std::stoi(argv[++i]);
        } else if (arg == "--loop-port" && i + 1 < argc) {
            out.loop_port = std::stoi(argv[++i]);
        } else if (arg == "--proof") {
            out.proof = true;
        } else if (arg == "--seconds" && i + 1 < argc) {
            out.seconds = std::stoi(argv[++i]);
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: audio_engine --host HOST --mic-port PORT --loop-port PORT [--proof --seconds N]\n";
            return false;
        } else {
            log_error("unknown arg: " + arg);
            return false;
        }
    }
    if (out.mic_port <= 0 || out.loop_port <= 0) {
        log_error("mic-port and loop-port are required");
        return false;
    }
    return true;
}

}  // namespace

int main(int argc, char **argv) {
    SetConsoleCtrlHandler(console_handler, TRUE);

    Args args;
    if (!parse_args(argc, argv, args)) {
        return 1;
    }

    if (args.proof) {
        run_proof(args.seconds);
        return 0;
    }

    WSADATA wsa_data;
    if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
        log_error("WSAStartup failed");
        return 1;
    }

    StreamConfig mic_cfg{"mic", args.host, args.mic_port, 440.0};
    StreamConfig loop_cfg{"loop", args.host, args.loop_port, 220.0};

    std::thread mic_thread(stream_worker, mic_cfg);
    std::thread loop_thread(stream_worker, loop_cfg);

    mic_thread.join();
    loop_thread.join();

    WSACleanup();
    return 0;
}
