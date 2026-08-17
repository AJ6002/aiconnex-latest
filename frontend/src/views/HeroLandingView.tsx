import React from 'react';
import { ViewMode } from '../types';

interface HeroLandingViewProps {
  onSelectView: (view: ViewMode) => void;
  onOpenChatBot?: () => void;
}

export const HeroLandingView: React.FC<HeroLandingViewProps> = ({ onSelectView, onOpenChatBot }) => {
  return (
    <div className="w-full bg-[#f7f9fb] text-[#191c1e] antialiased min-h-screen flex flex-col font-sans -mt-6 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8">
      {/* Top Bar Banner / Brand Announcement */}
      <div className="w-full max-w-[1440px] mx-auto pt-6 flex justify-between items-center pb-4 border-b border-[#c6c5ce]/30">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#2b0063] text-2xl font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>analytics</span>
          <span className="text-xl font-bold tracking-tight text-[#2b0063]">TAS AIConnex</span>
        </div>
        
        <div className="hidden md:flex items-center gap-6 text-sm">
          <span className="text-[#2b0063] font-bold border-b-2 border-[#2b0063] pb-1 cursor-pointer">Getting Started</span>
          <span className="text-[#46464e] font-medium hover:text-[#2b0063] transition-colors cursor-pointer" onClick={() => onSelectView('compiler')}>How It Works</span>
          <span className="text-[#46464e] font-medium hover:text-[#2b0063] transition-colors cursor-pointer" onClick={() => onSelectView('agent_manager')}>Agent Fleet</span>
          <span className="text-[#46464e] font-medium hover:text-[#2b0063] transition-colors cursor-pointer" onClick={() => onSelectView('templates')}>Pipelines</span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => onSelectView('compiler')}
            className="bg-[#E86326] hover:bg-[#D5521B] text-white font-bold text-xs sm:text-sm px-5 py-2.5 rounded-full transition-all shadow-md flex items-center gap-2 group cursor-pointer"
          >
            <span>Open AIConnex Studio</span>
            <span className="material-symbols-outlined text-sm sm:text-base text-white font-bold group-hover:translate-x-1 transition-transform">arrow_forward</span>
          </button>
        </div>
      </div>

      {/* Main Content Canvas */}
      <main className="flex-grow flex flex-col relative w-full max-w-[1440px] mx-auto overflow-hidden pt-12">
        {/* Hero Section */}
        <section className="px-4 sm:px-8 flex flex-col items-center text-center relative z-10 w-full mb-12">
          
          {/* Announcement Badge */}
          <div 
            onClick={() => onSelectView('compiler')}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#e6e8ea] border border-[#c6c5ce]/50 text-[#46464e] text-xs mb-8 hover:bg-[#e0e3e5] transition-colors cursor-pointer group shadow-sm"
          >
            <span className="bg-[#E86326] text-white px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider">New</span>
            <span>AIConnex 4-Layer Compiler is live — Explore the workflow</span>
            <span className="material-symbols-outlined text-[14px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
          </div>

          {/* Hero Typography */}
          <h1 className="text-3xl sm:text-5xl lg:text-6xl font-black text-[#2b0063] max-w-5xl mb-6 tracking-tight leading-tight">
            Industrial AI, from raw sensor data to edge-ready models in minutes.
          </h1>

          <p className="text-base sm:text-lg text-[#46464e] max-w-3xl mb-10 leading-relaxed">
            Turn multi-table industrial sensor archives into predictive-maintenance models through an agent-guided AutoML workflow built for plant engineers, data teams, and operations leaders.
          </p>

          {/* Call to Actions */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 w-full sm:w-auto">
            <button
              onClick={() => onSelectView('compiler')}
              className="w-full sm:w-auto bg-[#E86326] hover:bg-[#D5521B] text-white font-bold px-8 py-3.5 rounded-full flex items-center justify-center gap-2 transition-all shadow-lg hover:shadow-xl active:scale-95 duration-200 group cursor-pointer text-sm sm:text-base"
            >
              <span>Try the AI Agent</span>
              <span className="material-symbols-outlined text-[18px] text-white font-bold group-hover:translate-x-1 transition-transform">arrow_forward</span>
            </button>

            <button
              onClick={() => {
                fetch('http://localhost:8000/api/v1/pipeline/execute_end_to_end', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ file_name: 'C-MAPSS_FD001_train.csv', intent: 'turbofan_remaining_useful_life' }),
                })
                  .then((res) => res.json())
                  .then((data) => {
                    const dest = data.deployment_deliverables?.target_destination_view === 'DataStudio' ? 'data_explorer' : 'ml_studio';
                    onSelectView(dest as ViewMode);
                  })
                  .catch(() => {
                    onSelectView('ml_studio');
                  });
              }}
              className="w-full sm:w-auto bg-[#2B0063] hover:bg-[#3C1053] text-white font-bold px-8 py-3.5 rounded-full flex items-center justify-center gap-2 transition-all shadow-lg hover:shadow-xl active:scale-95 duration-200 group cursor-pointer text-sm sm:text-base border border-[#E86326]/40"
            >
              <span className="material-symbols-outlined text-[18px] text-[#E86326]">bolt</span>
              <span>⚡ Run End-to-End Pipeline (Offline)</span>
            </button>

            <button
              onClick={onOpenChatBot}
              className="w-full sm:w-auto bg-[#ffffff] border border-[#0D1533] text-[#0D1533] font-semibold px-6 py-3.5 rounded-full flex items-center justify-center gap-2 hover:bg-[#f2f4f6] transition-colors active:scale-95 duration-200 cursor-pointer text-sm sm:text-base shadow-sm"
            >
              <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
              <span>Ask AI Copilot</span>
            </button>
          </div>

          {/* Trust Strip */}
          <div className="flex flex-col items-center mb-12 w-full max-w-5xl">
            <p className="text-[11px] sm:text-xs text-[#76767e] mb-5 uppercase tracking-widest text-center font-semibold">
              Built for industrial telemetry, predictive maintenance, and edge deployment
            </p>
            <div className="flex flex-wrap justify-center items-center gap-6 sm:gap-12 opacity-80 transition-all duration-500">
              <div className="flex items-center gap-2 text-sm sm:text-base text-[#2b0063] font-extrabold tracking-wide">
                <span className="material-symbols-outlined text-xl">settings_input_component</span> OPC UA
              </div>
              <div className="flex items-center gap-2 text-sm sm:text-base text-[#2b0063] font-extrabold tracking-wide">
                <span className="material-symbols-outlined text-xl">router</span> MQTT
              </div>
              <div className="flex items-center gap-2 text-sm sm:text-base text-[#2b0063] font-extrabold tracking-wide">
                <span className="material-symbols-outlined text-xl">lan</span> Modbus TCP
              </div>
              <div className="flex items-center gap-2 text-sm sm:text-base text-[#2b0063] font-extrabold tracking-wide">
                <span className="material-symbols-outlined text-xl">model_training</span> ONNX
              </div>
            </div>
          </div>

          {/* Interactive Jane Hero Chat Assistant Section */}
          <div className="w-full max-w-[900px] mx-auto mb-16 bg-white rounded-3xl border-2 border-[#2b0063]/15 shadow-xl p-6 text-left relative overflow-hidden">
            <div className="flex items-center justify-between pb-4 mb-4 border-b border-[#c6c5ce]/30">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-[#2b0063] to-[#E86326] flex items-center justify-center text-white shadow-md">
                  <span className="material-symbols-outlined text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
                </div>
                <div>
                  <h3 className="font-bold text-[#2b0063] text-base flex items-center gap-2">
                    Jane Operations Assistant
                    <span className="bg-[#E86326]/10 text-[#E86326] text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wider">Online</span>
                  </h3>
                  <p className="text-xs text-[#76767e]">AI-Connex Onboarding & Data Integration Guide</p>
                </div>
              </div>

              <button
                onClick={() => onSelectView('compiler')}
                className="bg-[#2b0063] hover:bg-[#1e0046] text-white text-xs font-bold px-4 py-2 rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
              >
                <span>Upload Controller</span>
                <span className="material-symbols-outlined text-sm">cloud_upload</span>
              </button>
            </div>

            {/* Simulated Jane Onboarding Chat */}
            <div className="bg-[#f8fafc] rounded-2xl p-4 border border-slate-200/80 mb-4 space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-lg bg-[#2b0063] text-white flex items-center justify-center text-xs font-bold flex-shrink-0">J</div>
                <div className="bg-white p-3.5 rounded-2xl rounded-tl-none border border-slate-200 shadow-sm text-xs sm:text-sm text-slate-700 leading-relaxed max-w-xl">
                  Welcome to <strong>AIConnex</strong>! I am Jane, your industrial AI copilot. How would you like to provide your sensor telemetry data today?
                </div>
              </div>

              {/* Action Prompt Chips */}
              <div className="flex flex-wrap gap-2 pt-1 pl-10">
                <button
                  onClick={() => onSelectView('compiler')}
                  className="bg-white hover:bg-[#E86326] hover:text-white text-[#2b0063] border border-[#2b0063]/30 font-semibold text-xs px-3.5 py-2 rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">upload_file</span>
                  <span>Upload Local Files (.csv, .parquet, .zip)</span>
                </button>

                <button
                  onClick={() => onSelectView('compiler')}
                  className="bg-white hover:bg-[#2b0063] hover:text-white text-[#2b0063] border border-[#2b0063]/30 font-semibold text-xs px-3.5 py-2 rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">cloud</span>
                  <span>Connect AWS S3 Bucket</span>
                </button>

                <button
                  onClick={() => onSelectView('compiler')}
                  className="bg-white hover:bg-[#2b0063] hover:text-white text-[#2b0063] border border-[#2b0063]/30 font-semibold text-xs px-3.5 py-2 rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">database</span>
                  <span>Connect PostgreSQL / Snowflake DB</span>
                </button>

                <button
                  onClick={() => onSelectView('compiler')}
                  className="bg-white hover:bg-[#2b0063] hover:text-white text-[#2b0063] border border-[#2b0063]/30 font-semibold text-xs px-3.5 py-2 rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">sensors</span>
                  <span>OPC UA / MQTT Stream</span>
                </button>
              </div>

              {/* Direct Launch Upload Banner Card */}
              <div className="ml-10 bg-gradient-to-r from-[#2b0063] to-[#430894] rounded-2xl p-4 text-white shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="material-symbols-outlined text-3xl text-[#E86326] bg-white/10 p-2 rounded-xl">cloud_upload</span>
                  <div>
                    <h4 className="font-bold text-sm">Launch Universal Upload Controller</h4>
                    <p className="text-xs text-white/70">Support for drag & drop, S3, SQL DBs, and live streams</p>
                  </div>
                </div>
                <button
                  onClick={() => onSelectView('compiler')}
                  className="w-full sm:w-auto bg-[#E86326] hover:bg-[#d4541c] text-white font-bold text-xs px-5 py-2.5 rounded-xl transition-all shadow-md flex items-center justify-center gap-1.5 cursor-pointer flex-shrink-0"
                >
                  <span>Open Controller</span>
                  <span className="material-symbols-outlined text-sm">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>

          {/* Visual Product Preview with Ambient Radial Glow */}
          <div className="relative w-full max-w-[1100px] mx-auto mt-4 mb-16 rounded-2xl p-1">
            {/* Ambient Radial Glow */}
            <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[#FFD8A8]/40 via-[#E86326]/20 to-[#2B0063]/10 blur-3xl rounded-full translate-y-[-5%] scale-105 opacity-75 pointer-events-none"></div>

            {/* Browser / Product Card Shell */}
            <div className="bg-white rounded-2xl border border-[#c6c5ce]/40 shadow-[0_16px_40px_rgba(13,21,51,0.08)] overflow-hidden w-full relative group">
              {/* Browser Header */}
              <div className="h-10 bg-[#eceef0] flex items-center px-4 border-b border-[#c6c5ce]/30 gap-2">
                <div className="w-3 h-3 rounded-full bg-red-400"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-400"></div>
                <div className="w-3 h-3 rounded-full bg-green-400"></div>
                <div className="mx-auto bg-white border border-[#c6c5ce]/40 rounded-md h-6 px-6 flex items-center justify-center text-[11px] text-[#46464e] font-mono">
                  <span className="material-symbols-outlined text-[12px] mr-1 text-[#76767e]">lock</span> aiconnex.industrial.ai/workspace
                </div>
              </div>

              {/* Main App Interactive Showcase */}
              <div className="relative aspect-video w-full bg-[#1e1b2e] p-6 text-white flex flex-col justify-between overflow-hidden">
                {/* Overlay Badge */}
                <div className="flex justify-between items-center z-10">
                  <span className="bg-white/90 backdrop-blur-sm border border-[#c6c5ce]/30 text-[#2b0063] text-xs font-bold px-3 py-1.5 rounded-full shadow-sm flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#E86326] animate-pulse"></span>
                    Platform Active • Universal Data Entry & ML Pipeline
                  </span>

                  <button
                    onClick={() => onSelectView('compiler')}
                    className="bg-[#E86326] hover:bg-[#D5521B] text-white text-xs font-bold px-4 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-1 cursor-pointer"
                  >
                    <span>Launch Controller</span>
                    <span className="material-symbols-outlined text-xs">open_in_new</span>
                  </button>
                </div>

                {/* Simulated Pipeline Graph View */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 my-auto z-10 pt-4">
                  <div 
                    onClick={() => onSelectView('compiler')}
                    className="bg-[#2B0063]/80 border border-[#E86326]/40 p-4 rounded-2xl cursor-pointer hover:border-[#E86326] transition-all hover:scale-105"
                  >
                    <div className="flex items-center gap-2 text-[#E86326] font-bold text-xs uppercase mb-1">
                      <span className="material-symbols-outlined text-sm">cloud_upload</span>
                      <span>1. Upload Controller</span>
                    </div>
                    <p className="text-xs text-white/80">Local files, S3 bucket, Cloud SQL & industrial stream ingestion</p>
                  </div>

                  <div 
                    onClick={() => onSelectView('data_explorer')}
                    className="bg-[#2B0063]/80 border border-white/15 p-4 rounded-2xl cursor-pointer hover:border-[#E86326] transition-all hover:scale-105"
                  >
                    <div className="flex items-center gap-2 text-white font-bold text-xs uppercase mb-1">
                      <span className="material-symbols-outlined text-sm text-[#E86326]">analytics</span>
                      <span>2. Data Explorer</span>
                    </div>
                    <p className="text-xs text-white/80">Cleaned dataset statistics, profile checks & temporal features</p>
                  </div>

                  <div 
                    onClick={() => onSelectView('pipeline_studio')}
                    className="bg-[#2B0063]/80 border border-white/15 p-4 rounded-2xl cursor-pointer hover:border-[#E86326] transition-all hover:scale-105"
                  >
                    <div className="flex items-center gap-2 text-white font-bold text-xs uppercase mb-1">
                      <span className="material-symbols-outlined text-sm text-[#E86326]">monitoring</span>
                      <span>3. ML Pipeline Studio</span>
                    </div>
                    <p className="text-xs text-white/80">AutoML model training, evaluation & edge deployment</p>
                  </div>
                </div>

                <div className="text-[11px] text-white/40 font-mono text-center z-10">
                  Click any stage above to launch into the full AI-ConneX interactive workspace
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── ACCESSIBILITY FEATURE: Interactive Studio Mini-Boxes ── */}
        <section className="px-4 sm:px-8 max-w-[1440px] mx-auto w-full mb-16 relative z-10">
          <div className="text-center mb-8 space-y-2">
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-[#E86326] bg-[#E86326]/10 px-3 py-1 rounded-full border border-[#E86326]/30">
              ⚡ User Accessibility Quick Launch
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-[#2b0063] tracking-tight">
              Direct Accessibility Studios & Metaphorical Agent Workspaces
            </h2>
            <p className="text-xs sm:text-sm text-[#46464e] font-mono max-w-2xl mx-auto">
              Instant one-click access to Data Studio, ML Studio, Physics Gateway, and Agent Fleet.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Mini Box 1: Data Studio */}
            <div
              onClick={() => onSelectView('compiler')}
              className="bg-white border border-[#c6c5ce]/40 p-6 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer group flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-[#E86326]/10 text-[#E86326] flex items-center justify-center font-bold group-hover:bg-[#E86326] group-hover:text-white transition-colors">
                  <span className="material-symbols-outlined text-2xl">cloud_upload</span>
                </div>
                <h3 className="font-bold text-lg text-[#2b0063] group-hover:text-[#E86326] transition-colors">
                  Data Studio & Ingestion
                </h3>
                <p className="text-xs text-[#46464e] leading-relaxed">
                  Universal upload controller supporting Local Files, AWS S3, Cloud SQL, and OPC UA telemetry streams.
                </p>
              </div>
              <div className="pt-4 border-t border-[#c6c5ce]/20 flex items-center justify-between text-xs font-bold text-[#E86326]">
                <span>Launch Data Studio</span>
                <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </div>
            </div>

            {/* Mini Box 2: ML Studio & AutoML Ledger */}
            <div
              onClick={() => onSelectView('model_explorer')}
              className="bg-white border border-[#c6c5ce]/40 p-6 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer group flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-[#2B0063]/10 text-[#2B0063] flex items-center justify-center font-bold group-hover:bg-[#2B0063] group-hover:text-white transition-colors">
                  <span className="material-symbols-outlined text-2xl">auto_graph</span>
                </div>
                <h3 className="font-bold text-lg text-[#2b0063] group-hover:text-[#2B0063] transition-colors">
                  ML Studio & Model Ledger
                </h3>
                <p className="text-xs text-[#46464e] leading-relaxed">
                  Competitive AutoML training, Recipe Orchestrator, SHAP feature importances & Sankey flow matrix.
                </p>
              </div>
              <div className="pt-4 border-t border-[#c6c5ce]/20 flex items-center justify-between text-xs font-bold text-[#2B0063]">
                <span>Launch ML Studio</span>
                <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </div>
            </div>

            {/* Mini Box 3: Deployment Studio & Physics Layer */}
            <div
              onClick={() => onSelectView('deployment')}
              className="bg-white border border-[#c6c5ce]/40 p-6 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer group flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-purple-500/10 text-purple-600 flex items-center justify-center font-bold group-hover:bg-purple-600 group-hover:text-white transition-colors">
                  <span className="material-symbols-outlined text-2xl">rocket_launch</span>
                </div>
                <h3 className="font-bold text-lg text-[#2b0063] group-hover:text-purple-600 transition-colors">
                  Deployment & Physics
                </h3>
                <p className="text-xs text-[#46464e] leading-relaxed">
                  Mathematical physics layers (FFT, Exponential Decay, Z-Score), visual dials & ONNX Edge Gateway.
                </p>
              </div>
              <div className="pt-4 border-t border-[#c6c5ce]/20 flex items-center justify-between text-xs font-bold text-purple-600">
                <span>Launch Deployment</span>
                <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </div>
            </div>

            {/* Mini Box 4: Agent Fleet Orchestrator */}
            <div
              onClick={() => onSelectView('agent_manager')}
              className="bg-white border border-[#c6c5ce]/40 p-6 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer group flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center font-bold group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                  <span className="material-symbols-outlined text-2xl">smart_toy</span>
                </div>
                <h3 className="font-bold text-lg text-[#2b0063] group-hover:text-emerald-600 transition-colors">
                  Agent Fleet Orchestrator
                </h3>
                <p className="text-xs text-[#46464e] leading-relaxed">
                  Tri-LLM Metaphorical Agents & 7-Node Executors operating in real-time closed-loop synchronization.
                </p>
              </div>
              <div className="pt-4 border-t border-[#c6c5ce]/20 flex items-center justify-between text-xs font-bold text-emerald-600">
                <span>Launch Agent Fleet</span>
                <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="w-full py-12 border-t border-[#c6c5ce]/30 mt-auto bg-[#f2f4f6]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[#2b0063] font-bold text-lg">
              <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>analytics</span>
              <span>TAS AIConnex</span>
            </div>
            <p className="text-xs text-[#46464e] max-w-sm">
              Enterprise-grade industrial AutoML platform for technical engineering and operations.
            </p>
            <div className="text-xs text-[#76767e] mt-2">
              © 2026 AIConnex Industrial Systems. All rights reserved.
            </div>
          </div>

          <div className="flex flex-col gap-2 text-xs">
            <h4 className="text-[#2b0063] font-bold mb-1">Product</h4>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer" onClick={() => onSelectView('compiler')}>Compiler Studio</span>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer" onClick={() => onSelectView('agent_manager')}>Agent Fleet</span>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer" onClick={() => onSelectView('templates')}>ML Pipelines</span>
          </div>

          <div className="flex flex-col gap-2 text-xs">
            <h4 className="text-[#2b0063] font-bold mb-1">Platform</h4>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer">OPC UA / MQTT</span>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer">ONNX Edge Export</span>
            <span className="text-[#46464e] hover:text-[#2b0063] cursor-pointer">Jane Assistant</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
