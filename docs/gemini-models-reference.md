# Gemini Models Reference

Complete reference for all available Gemini models across Google AI Studio and Vertex AI (GCloud).

## Currently Active Configuration

**Provider:** `google-ai-studio`
**Default Model:** `gemini-2.0-flash-exp`
**Fallback Model:** `gemini-1.5-pro`

---

## Google AI Studio Models (Current Provider)

### 🧪 Experimental Models (Latest Features)
| Model | Description | Best For |
|-------|-------------|----------|
| `gemini-2.0-flash-exp` | Latest Flash experimental | Fast responses, high throughput |
| `gemini-2.0-flash-thinking-exp-1219` | Flash with enhanced reasoning | Complex problem-solving |
| `gemini-exp-1206` | Experimental release (Dec 6) | Testing latest features |
| `gemini-exp-1121` | Experimental release (Nov 21) | Testing new capabilities |
| `learnlm-1.5-pro-experimental` | Learning-focused model | Educational content |

### ✅ Stable Models (Production Ready)
| Model | Description | Context | Best For |
|-------|-------------|---------|----------|
| `gemini-1.5-pro` | Most capable stable model | 2M tokens | Complex tasks, long context |
| `gemini-1.5-pro-002` | Optimized Pro variant | 2M tokens | Production workloads |
| `gemini-1.5-flash` | Fast, efficient model | 1M tokens | Quick responses |
| `gemini-1.5-flash-002` | Optimized Flash variant | 1M tokens | High-volume APIs |
| `gemini-1.5-flash-8b` | Smallest Flash model | 1M tokens | Cost-sensitive apps |
| `gemini-1.0-pro` | Legacy stable model | 32K tokens | Compatibility |

### 👁️ Vision Models
| Model | Description | Capabilities |
|-------|-------------|--------------|
| `gemini-1.5-pro` | Pro with vision | Image, video analysis |
| `gemini-1.5-flash` | Flash with vision | Fast image processing |
| `gemini-pro-vision` | Legacy vision model | Basic image tasks |

---

## Vertex AI (GCloud) Models

### Production Models (Vertex AI)
| Model ID | Description | Context | Region Availability |
|----------|-------------|---------|---------------------|
| `gemini-2.0-flash-001` | Gemini 2.0 Flash | 1M tokens | us-central1, europe-west1 |
| `gemini-1.5-pro-002` | Gemini 1.5 Pro | 2M tokens | All regions |
| `gemini-1.5-flash-002` | Gemini 1.5 Flash | 1M tokens | All regions |
| `gemini-1.0-pro-002` | Gemini 1.0 Pro | 32K tokens | All regions |

### Preview Models (Vertex AI)
| Model ID | Description | Access |
|----------|-------------|--------|
| `gemini-2.0-pro-exp` | Gemini 2.0 Pro (experimental) | Limited preview |
| `gemini-ultra-preview` | Ultra model preview | Waitlist only |

### Specialized Models (Vertex AI)
| Model ID | Purpose | Use Case |
|----------|---------|----------|
| `gemini-nano` | On-device model | Edge computing, mobile |
| `text-bison@002` | Legacy text model | Migration support |
| `code-bison@002` | Legacy code model | Code generation |

---

## Switching Between Providers

### Current: Google AI Studio (API Key)
```json
{
  "gemini": {
    "provider": "google-ai-studio",
    "default_model": "gemini-2.0-flash-exp"
  }
}
```

**Pros:**
- ✅ Pay-as-you-go pricing
- ✅ 4M tokens/minute
- ✅ Simple API key auth
- ✅ Latest experimental models

### Alternative: Vertex AI (GCloud)
```json
{
  "gemini": {
    "provider": "vertex-ai",
    "project_id": "jrpm-dev",
    "location": "us-central1",
    "default_model": "gemini-2.0-flash-001"
  }
}
```

**Pros:**
- ✅ Enterprise SLAs
- ✅ VPC integration
- ✅ Advanced IAM
- ✅ Audit logging
- ✅ Regional deployment

---

## Rate Limits by Provider

### Google AI Studio (Current)
```json
{
  "rate_limiting": {
    "requests_per_minute": 1000,
    "tokens_per_minute": 4000000,
    "concurrent_requests": 10
  }
}
```

### Vertex AI
```json
{
  "rate_limiting": {
    "requests_per_minute": 300,
    "tokens_per_minute": 30000,
    "concurrent_requests": 5
  }
}
```
*Note: Vertex AI limits vary by quota allocation*

---

## Model Selection Guide

### When to Use Each Model

**gemini-2.0-flash-exp** (Default)
- ⚡ Fast responses needed
- 💰 Cost-sensitive applications
- 🔄 High-volume APIs
- ✨ Want latest features

**gemini-1.5-pro**
- 🧠 Complex reasoning required
- 📚 Long context (2M tokens)
- 🎯 Accuracy critical
- 📊 Production stability needed

**gemini-2.0-flash-thinking-exp**
- 🤔 Multi-step reasoning
- 🧩 Problem-solving tasks
- 📈 Chain-of-thought needed
- 🔬 Research applications

**gemini-1.5-flash-8b**
- 💸 Budget constraints
- ⚡ Speed over capability
- 📱 Simple tasks
- 🔁 High request volume

---

## Configuration Files

**User-level:** `~/.gemini/settings.json`
**Project-level:** `GCP_LOGGING/.gemini/settings.json`
**Antigravity:** `~/.gemini/antigravity/mcp_config.json`

All configurations are synchronized with the same model availability.

---

## API Keys & Authentication

**Google AI Studio Key:** `~/.secrets/google_ai_studio_gemini.key`
**Environment Variable:** `GEMINI_API_KEY` (auto-loaded via `.bashrc`)
**Auth Type:** `gemini-api-key`

For Vertex AI, use gcloud authentication:
```bash
gcloud auth application-default login
```

---

## Updating Models

To change the default model, edit the configuration:

```bash
# Edit user-level settings
vim ~/.gemini/settings.json

# Or edit project-level settings
vim .gemini/settings.json
```

Change the `default_model` field to any model from the `available_models` list.
