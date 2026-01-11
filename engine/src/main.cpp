// Audio Engine with WASAPI Capture
// Captures microphone and loopback audio and sends via TCP

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>
#include <iostream>
#include <thread>
#include <chrono>
#include <vector>
#include <cmath>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "ole32.lib")

// WASAPI constants
const CLSID CLSID_MMDeviceEnumerator = __uuidof(MMDeviceEnumerator);
const IID IID_IMMDeviceEnumerator = __uuidof(IMMDeviceEnumerator);
const IID IID_IAudioClient = __uuidof(IAudioClient);
const IID IID_IAudioCaptureClient = __uuidof(IAudioCaptureClient);

const int MIC_PORT = 17711;
const int LOOPBACK_PORT = 17712;
const int FRAME_SIZE = 1920;  // 960 samples * 2 bytes (20ms at 48kHz mono int16)
const int FRAME_INTERVAL_MS = 20;
const int SAMPLE_RATE = 48000;
const int SAMPLES_PER_FRAME = 960;  // 20ms at 48kHz

enum DeviceType {
    DEVICE_MIC,
    DEVICE_LOOPBACK
};

// Helper function to convert float samples to int16
void convert_float_to_int16(const float* input, int16_t* output, int num_samples) {
    for (int i = 0; i < num_samples; i++) {
        float sample = input[i];
        // Clamp to [-1.0, 1.0]
        if (sample > 1.0f) sample = 1.0f;
        if (sample < -1.0f) sample = -1.0f;
        // Convert to int16 range
        output[i] = static_cast<int16_t>(sample * 32767.0f);
    }
}

// Helper function to convert stereo to mono
void convert_stereo_to_mono(const int16_t* stereo, int16_t* mono, int num_frames) {
    for (int i = 0; i < num_frames; i++) {
        // Average left and right channels
        int32_t avg = (static_cast<int32_t>(stereo[i * 2]) + static_cast<int32_t>(stereo[i * 2 + 1])) / 2;
        mono[i] = static_cast<int16_t>(avg);
    }
}

void send_wasapi_audio(SOCKET client_socket, const char* stream_name, DeviceType device_type) {
    HRESULT hr;
    
    // Initialize COM
    hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] COM initialization failed: 0x" << std::hex << hr << std::endl;
        closesocket(client_socket);
        return;
    }
    
    IMMDeviceEnumerator* pEnumerator = nullptr;
    IMMDevice* pDevice = nullptr;
    IAudioClient* pAudioClient = nullptr;
    IAudioCaptureClient* pCaptureClient = nullptr;
    WAVEFORMATEX* pwfx = nullptr;
    
    // Create device enumerator
    hr = CoCreateInstance(
        CLSID_MMDeviceEnumerator, nullptr,
        CLSCTX_ALL, IID_IMMDeviceEnumerator,
        (void**)&pEnumerator);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to create device enumerator: 0x" << std::hex << hr << std::endl;
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    // Get default device
    EDataFlow dataFlow = (device_type == DEVICE_MIC) ? eCapture : eRender;
    hr = pEnumerator->GetDefaultAudioEndpoint(dataFlow, eConsole, &pDevice);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to get default audio endpoint: 0x" << std::hex << hr << std::endl;
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    // Activate audio client
    hr = pDevice->Activate(IID_IAudioClient, CLSCTX_ALL, nullptr, (void**)&pAudioClient);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to activate audio client: 0x" << std::hex << hr << std::endl;
        pDevice->Release();
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    // Get the device's mix format
    hr = pAudioClient->GetMixFormat(&pwfx);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to get mix format: 0x" << std::hex << hr << std::endl;
        pAudioClient->Release();
        pDevice->Release();
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    std::cout << "[" << stream_name << "] Device format: " << pwfx->nSamplesPerSec << "Hz, " 
              << pwfx->nChannels << " channels, " << pwfx->wBitsPerSample << " bits" << std::endl;
    
    // Initialize audio client
    DWORD streamFlags = (device_type == DEVICE_LOOPBACK) ? AUDCLNT_STREAMFLAGS_LOOPBACK : 0;
    
    hr = pAudioClient->Initialize(
        AUDCLNT_SHAREMODE_SHARED,
        streamFlags,
        10000000,  // 1 second buffer
        0,
        pwfx,
        nullptr);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to initialize audio client: 0x" << std::hex << hr << std::endl;
        CoTaskMemFree(pwfx);
        pAudioClient->Release();
        pDevice->Release();
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    // Get capture client
    hr = pAudioClient->GetService(IID_IAudioCaptureClient, (void**)&pCaptureClient);
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to get capture client: 0x" << std::hex << hr << std::endl;
        CoTaskMemFree(pwfx);
        pAudioClient->Release();
        pDevice->Release();
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    // Start audio capture
    hr = pAudioClient->Start();
    
    if (FAILED(hr)) {
        std::cerr << "[" << stream_name << "] Failed to start audio client: 0x" << std::hex << hr << std::endl;
        pCaptureClient->Release();
        CoTaskMemFree(pwfx);
        pAudioClient->Release();
        pDevice->Release();
        pEnumerator->Release();
        CoUninitialize();
        closesocket(client_socket);
        return;
    }
    
    std::cout << "[" << stream_name << "] Audio capture started successfully" << std::endl;
    
    // Capture and send audio
    std::vector<int16_t> output_buffer(SAMPLES_PER_FRAME);
    std::vector<int16_t> accumulated_buffer;
    int sample_count = 0;
    bool is_float = (pwfx->wFormatTag == WAVE_FORMAT_IEEE_FLOAT || 
                     (pwfx->wFormatTag == WAVE_FORMAT_EXTENSIBLE && 
                      ((WAVEFORMATEXTENSIBLE*)pwfx)->SubFormat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT));
    
    while (true) {
        BYTE* pData;
        UINT32 numFramesAvailable;
        DWORD flags;
        
        // Get available data
        hr = pCaptureClient->GetBuffer(&pData, &numFramesAvailable, &flags, nullptr, nullptr);
        
        if (hr == AUDCLNT_S_BUFFER_EMPTY) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }
        
        if (FAILED(hr)) {
            std::cerr << "[" << stream_name << "] GetBuffer failed: 0x" << std::hex << hr << std::endl;
            break;
        }
        
        if (numFramesAvailable > 0) {
            std::vector<int16_t> temp_buffer;
            
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                // Silent buffer, fill with zeros
                temp_buffer.resize(numFramesAvailable, 0);
            } else {
                // Convert audio to mono int16
                if (is_float) {
                    // Float format
                    const float* float_data = reinterpret_cast<const float*>(pData);
                    
                    if (pwfx->nChannels == 1) {
                        // Mono float to mono int16
                        temp_buffer.resize(numFramesAvailable);
                        convert_float_to_int16(float_data, temp_buffer.data(), numFramesAvailable);
                    } else {
                        // Stereo float to mono int16
                        std::vector<int16_t> stereo_buffer(numFramesAvailable * 2);
                        convert_float_to_int16(float_data, stereo_buffer.data(), numFramesAvailable * 2);
                        temp_buffer.resize(numFramesAvailable);
                        convert_stereo_to_mono(stereo_buffer.data(), temp_buffer.data(), numFramesAvailable);
                    }
                } else {
                    // Int16 format
                    const int16_t* int16_data = reinterpret_cast<const int16_t*>(pData);
                    
                    if (pwfx->nChannels == 1) {
                        // Already mono int16
                        temp_buffer.assign(int16_data, int16_data + numFramesAvailable);
                    } else {
                        // Stereo int16 to mono int16
                        temp_buffer.resize(numFramesAvailable);
                        convert_stereo_to_mono(int16_data, temp_buffer.data(), numFramesAvailable);
                    }
                }
            }
            
            // Add to accumulated buffer
            accumulated_buffer.insert(accumulated_buffer.end(), temp_buffer.begin(), temp_buffer.end());
            
            // Send complete frames
            while (accumulated_buffer.size() >= SAMPLES_PER_FRAME) {
                // Copy one frame to output buffer
                std::copy(accumulated_buffer.begin(), 
                         accumulated_buffer.begin() + SAMPLES_PER_FRAME, 
                         output_buffer.begin());
                
                // Send via TCP
                int sent = send(client_socket, 
                               reinterpret_cast<const char*>(output_buffer.data()), 
                               FRAME_SIZE, 0);
                
                if (sent == SOCKET_ERROR || sent == 0) {
                    std::cerr << "[" << stream_name << "] Client disconnected" << std::endl;
                    pCaptureClient->ReleaseBuffer(numFramesAvailable);
                    goto cleanup;
                }
                
                // Remove sent samples from accumulated buffer
                accumulated_buffer.erase(accumulated_buffer.begin(), 
                                        accumulated_buffer.begin() + SAMPLES_PER_FRAME);
                
                sample_count++;
                
                if (sample_count % 50 == 0) {
                    std::cout << "[" << stream_name << "] Sent " << (sample_count * FRAME_SIZE) << " bytes" << std::endl;
                }
            }
        }
        
        pCaptureClient->ReleaseBuffer(numFramesAvailable);
    }
    
cleanup:
    // Stop audio
    pAudioClient->Stop();
    
    // Release resources
    pCaptureClient->Release();
    CoTaskMemFree(pwfx);
    pAudioClient->Release();
    pDevice->Release();
    pEnumerator->Release();
    
    CoUninitialize();
    closesocket(client_socket);
    
    std::cout << "[" << stream_name << "] Audio capture stopped" << std::endl;
}

void handle_stream(int port, const char* stream_name, DeviceType device_type) {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "WSAStartup failed" << std::endl;
        return;
    }
    
    SOCKET listen_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_socket == INVALID_SOCKET) {
        std::cerr << "Socket creation failed" << std::endl;
        WSACleanup();
        return;
    }
    
    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    server_addr.sin_port = htons(port);
    
    if (bind(listen_socket, (sockaddr*)&server_addr, sizeof(server_addr)) == SOCKET_ERROR) {
        std::cerr << "Bind failed on port " << port << std::endl;
        closesocket(listen_socket);
        WSACleanup();
        return;
    }
    
    if (listen(listen_socket, 1) == SOCKET_ERROR) {
        std::cerr << "Listen failed" << std::endl;
        closesocket(listen_socket);
        WSACleanup();
        return;
    }
    
    std::cout << "[" << stream_name << "] Listening on port " << port << std::endl;
    
    while (true) {
        sockaddr_in client_addr;
        int client_addr_len = sizeof(client_addr);
        SOCKET client_socket = accept(listen_socket, (sockaddr*)&client_addr, &client_addr_len);
        
        if (client_socket == INVALID_SOCKET) {
            std::cerr << "Accept failed" << std::endl;
            continue;
        }
        
        std::cout << "[" << stream_name << "] Client connected from " 
                  << inet_ntoa(client_addr.sin_addr) << std::endl;
        
        // Handle client in separate thread
        std::thread client_thread(send_wasapi_audio, client_socket, stream_name, device_type);
        client_thread.detach();
    }
    
    closesocket(listen_socket);
    WSACleanup();
}

int main() {
    std::cout << "Audio Engine v2 - WASAPI Capture" << std::endl;
    std::cout << "Port " << MIC_PORT << " = Microphone" << std::endl;
    std::cout << "Port " << LOOPBACK_PORT << " = Loopback" << std::endl;
    std::cout << "Capturing real audio: 48kHz, mono, int16, 20ms frames" << std::endl;
    std::cout << std::endl;
    
    // Start mic stream server
    std::thread mic_thread(handle_stream, MIC_PORT, "MIC", DEVICE_MIC);
    
    // Start loopback stream server
    std::thread loopback_thread(handle_stream, LOOPBACK_PORT, "LOOPBACK", DEVICE_LOOPBACK);
    
    // Wait for threads
    mic_thread.join();
    loopback_thread.join();
    
    return 0;
}
