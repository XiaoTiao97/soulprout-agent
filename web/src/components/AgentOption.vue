<!-- AgentOption.vue -->
<template>
  <div class="agent-option-overlay" @click="handleOverlayClick">
    <div class="agent-option-container" @click.stop>
      <div class="agent-option-header">
        <div class="header-title-group">
          <p class="header-eyebrow">EXPERTS</p>
          <div class="header-title-wrap">
            <h2>{{ t('agentOption.title') }}</h2>
            <span class="header-hint">{{ t('agentOption.headerHint') }}</span>
          </div>
        </div>

        <button class="close-btn" @click="$emit('close')" :aria-label="t('common.close')">
          <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M1 1L9 9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- 智能体内容 -->
      <div class="agent-content">
        <div class="agent-sidebar">
          <div class="create-agent" @click="startCreate" :title="t('agentOption.createAgent')">
            <div class="plus-box">
                <img src="@/assets/images/add_icon.svg" width="18" height="18" />
            </div>
          </div>
          <div v-if="loading" class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading agents...</p>
          </div>

          <div v-else-if="error" class="error-state">
            <p>{{ error }}</p>
            <button @click="fetchAgentList" class="retry-btn">Retry</button>
          </div>

          <div v-else class="agent-list">
            <!-- 我的创建（为空时也显示） -->
            <div class="agent-block">
              <div class="agent-block-header" @click="toggleBlock('myCreated')">
                <span class="agent-block-title">{{ t('messageInput.myCreated') }}</span>
                <svg class="block-toggle-icon" :class="{ expanded: expandedBlocks.myCreated }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
              </div>
              <div v-show="expandedBlocks.myCreated" class="agent-block-items">
                <div v-if="myCreatedAgents.length === 0" class="empty-block-hint">{{ t('agentOption.noCreated') }}</div>
                <div 
                  v-for="agent in myCreatedAgents" 
                  :key="agent.agent_id"
                  :class="['agent-item', { selected: selectedAgent && selectedAgent.agent_id === agent.agent_id }]"
                  @click="selectAgent(agent)"
                >
                  <h3 class="agent-name">{{ agent.name_zh || agent.name }}</h3>
                </div>
              </div>
            </div>
            <!-- 我的订阅（为空时也显示） -->
            <div class="agent-block">
              <div class="agent-block-header" @click="toggleBlock('mySubscribed')">
                <span class="agent-block-title">{{ t('messageInput.mySubscribed') }}</span>
                <svg class="block-toggle-icon" :class="{ expanded: expandedBlocks.mySubscribed }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
              </div>
              <div v-show="expandedBlocks.mySubscribed" class="agent-block-items">
                <button class="agent-market-btn" @click="openAgentMarket">
                  <img src="@/assets/images/agent_market.svg" alt="" class="agent-market-icon" width="18" height="18" />
                  <span>{{ t('agentOption.expertSubscribe') }}</span>
                </button>
                <div v-if="mySubscribedAgents.length === 0" class="empty-block-hint">{{ t('messageInput.noSubscription') }}</div>
                <div 
                  v-for="agent in mySubscribedAgents" 
                  :key="agent.agent_id"
                  :class="['agent-item', { selected: selectedAgent && selectedAgent.agent_id === agent.agent_id }]"
                  @click="selectAgent(agent)"
                >
                  <h3 class="agent-name">{{ agent.name_zh || agent.name }}</h3>
                </div>
              </div>
            </div>
            <!-- 系统预设 -->
            <div class="agent-block" v-if="systemPresetAgents.length > 0">
              <div class="agent-block-header" @click="toggleBlock('systemPreset')">
                <span class="agent-block-title">{{ t('messageInput.systemPreset') }}</span>
                <svg class="block-toggle-icon" :class="{ expanded: expandedBlocks.systemPreset }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
              </div>
              <div v-show="expandedBlocks.systemPreset" class="agent-block-items">
                <div 
                  v-for="agent in systemPresetAgents" 
                  :key="agent.agent_id"
                  :class="['agent-item', { selected: selectedAgent && selectedAgent.agent_id === agent.agent_id }]"
                  @click="selectAgent(agent)"
                >
                  <h3 class="agent-name">{{ agent.name_zh || agent.name }}</h3>
                </div>
              </div>
            </div>

            <!-- 空状态 -->
            <div v-if="filteredAgentList.length === 0" class="empty-state">
              <p>{{ t('agentOption.noExperts') }}</p>
            </div>
          </div>
        </div>

        <div class="agent-main">
          <div v-if="isCreating">
            <div class="agent-info" :class="{ 'is-readonly': !isEditing && !isCreating, 'is-editing': isEditing || isCreating }">
              <div class="agent-info-header">
                <div class="name-wrapper">
                  <h3>{{ t('agentOption.createAgentTitle') }}</h3>
                </div>
                <div class="agent-actions">
                  <button class="action-btn save-edit" @click="confirmCreate">{{ t('agentOption.create') }}</button>
                  <button class="action-btn cancel-edit" @click="cancelCreate">{{ t('common.cancel') }}</button>
                </div>
              </div>
              <div class="agent-info-content">
                <div class="field-group">
                  <label>{{ t('agentOption.model') }}<span class="required">*</span></label>
                  <div class="model-selector" ref="newModelSelectorRef">
                    <button class="model-select-btn" type="button" @click="toggleNewModelSelector">
                      <span>{{ newSelectedModelDisplay }}</span>
                      <svg class="dropdown-icon" :class="{ 'rotate': showNewModelSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                        <path d="M6 8L2 4h8l-4 4z"/>
                      </svg>
                    </button>
                    <div class="model-dropdown" v-show="showNewModelSelector">
                      <div v-for="provider in modelProviders" :key="provider.model_source" class="model-group">
                        <div class="model-group-title">{{ provider.model_source }}</div>
                        <button 
                          v-for="model in provider.models" 
                          :key="model.id"
                          class="model-option"
                          :class="{ 'active': newModel === model.id }"
                          type="button"
                          @click="selectNewModel(provider.model_source, model.id)"
                        >
                          {{ model.name }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.name') }}<span class="required">*</span></label>
                  <input v-model="newName" class="edit-input-agent" :placeholder="t('agentOption.namePlaceholder')">
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.nameZh') }}</label>
                  <input v-model="newNameZh" class="edit-input-agent" :placeholder="t('agentOption.nameZhPlaceholder')">
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.description') }}<span class="required">*</span></label>
                  <textarea v-model="newDescription" class="edit-textarea" :placeholder="t('agentOption.descriptionPlaceholder')"></textarea>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.systemPrompt') }}</label>
                  <textarea v-model="newSystemPrompt" class="edit-textarea" :placeholder="t('agentOption.systemPromptPlaceholder')"></textarea>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.historyInherit') }}</label>
                  <div class="history-toggle">
                    <div class="toggle-wrapper">
                      <label>{{ t('agentOption.mainAgentHistory') }}</label>
                      <div class="toggle" :class="{ active: newSupervisorHistory }" @click="newSupervisorHistory = !newSupervisorHistory">
                        <div class="toggle-circle"></div>
                      </div>
                      <span class="toggle-comment">{{ t('agentOption.historyInheritHint') }}</span>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.fileLibrary') }}</label>
                  <div class="file-library-wrapper">
                    <div class="list-selection agent-file-list">
                      <button class="upload-file-btn-inline" type="button" @click="triggerNewFileUpload" :title="t('agentOption.addFile')">
                        <img src="@/assets/images/file_upload.svg" width="18" height="18" />
                        <span>{{ t('agentOption.addFile') }}</span>
                      </button>
                      <div class="file-item" v-for="(file, idx) in newAgentFiles" :key="getNewFileKey(file, idx)">
                        <span class="file-name">{{ file.name }}</span>
                        <button class="remove-file-btn-inline" type="button" @click.stop="removeNewFile(idx)" :title="t('common.delete')">
                          <img :src="DeleteFileIconUrl" :alt="t('common.delete')" />
                        </button>
                      </div>
                      <div v-if="newAgentFiles.length === 0" class="empty-docs">{{ t('agentOption.noFiles') }}</div>
                    </div>
                  </div>
                </div>
                <!-- 公告暂时隐藏 -->
                <div class="field-group">
                  <label>{{ t('agentOption.tools') }}</label>
                  <div class="list-selection">
                    <div 
                      v-for="(tools, classZh) in groupedTools" 
                      :key="classZh"
                      class="tool-group"
                    >
                      <!-- 分组头部 -->
                      <div class="tool-group-header" @click="toggleToolGroup(classZh)">
                        <div class="tool-group-header-text">
                          <span class="tool-group-name">{{ classZh }}</span>
                          <span class="tool-group-count">{{ t('agentOption.toolCount', { n: tools.length }) }}</span>
                          <span v-if="getSelectedCountInGroup(classZh) > 0" class="tool-group-selected">
                            {{ t('agentOption.selectedCount', { n: getSelectedCountInGroup(classZh) }) }}
                          </span>
                        </div>
                        <div class="tool-group-toggle">
                          <svg 
                            :class="['toggle-icon', { expanded: expandedToolGroups.includes(classZh) }]"
                            width="16" 
                            height="16" 
                            viewBox="0 0 16 16" 
                            fill="none"
                          >
                            <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                          </svg>
                        </div>
                      </div>
                      <!-- 分组下的工具列表 -->
                      <div v-if="expandedToolGroups.includes(classZh)" class="tool-group-items">
                        <label v-for="tool in tools" :key="tool.name" class="list-item">
                          <div class="list-item-header">
                            <input type="checkbox" :id="'new-' + tool.name" :value="tool.name" v-model="selectedNewTools" />
                            <span class="list-title">{{ tool.name }}</span>
                          </div>
                          <span v-if="tool.description" class="list-desc">{{ tool.description }}</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.skills') }}</label>
                  <div class="skill-agent-section">
                    <div class="skill-agent-subsection">
                      <div class="skill-agent-subtitle">{{ t('agentOption.systemSkills') }}</div>
                      <div v-if="systemSkillsList.length === 0" class="empty-state">{{ t('agentOption.noSystemSkills') }}</div>
                      <div v-else class="list-selection">
                        <label v-for="skill in systemSkillsList" :key="'new-sys-' + skill.name" class="list-item">
                          <div class="list-item-header">
                            <input type="checkbox" :id="'new-skill-sys-' + skill.name" :value="skill.name" v-model="selectedNewSystemSkills" />
                            <span class="list-title">{{ skill.name }}</span>
                          </div>
                          <span v-if="skill.description" class="list-desc">{{ skill.description }}</span>
                        </label>
                      </div>
                    </div>
                    <div class="skill-agent-subsection">
                      <div class="skill-agent-subtitle">{{ t('agentOption.personalSkills') }}</div>
                      <div v-if="userSkillsList.length === 0" class="empty-state">{{ t('agentOption.noPersonalSkills') }}</div>
                      <div v-else class="list-selection">
                        <label v-for="skill in userSkillsList" :key="'new-user-' + skill.name" class="list-item">
                          <div class="list-item-header">
                            <input type="checkbox" :id="'new-skill-user-' + skill.name" :value="skill.name" v-model="selectedNewUserSkills" />
                            <span class="list-title">{{ skill.name }}</span>
                          </div>
                          <span v-if="skill.description" class="list-desc">{{ skill.description }}</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.subAgents') }}</label>
                  <div v-if="filteredSubAgents.length === 0" class="empty-state">{{ t('agentOption.noSubAgents') }}</div>
                  <div v-else class="list-selection">
                    <label v-for="agent in filteredSubAgents" :key="agent.agent_id" class="list-item">
                      <div class="list-item-header">
                        <input type="checkbox" :id="'new-sub-' + agent.agent_id" :value="agent.agent_id" v-model="selectedNewSubAgents" />
                        <span class="list-title">{{ agent.name }}</span>
                      </div>
                      <span v-if="agent.description" class="list-desc">{{ agent.description }}</span>
                    </label>
                  </div>
                </div>
                <div class="field-group">
                  <label>{{ t('agentOption.knowledgeBase') }}</label>
                  <div class="list-selection">
                    <label v-for="kb in allKbs" :key="kb.kb_id" class="list-item">
                      <div class="list-item-header">
                        <input type="checkbox" :id="'new-kb-' + kb.kb_id" :value="kb.kb_id" v-model="selectedNewKbs" />
                        <span class="list-title">{{ kb.name }}</span>
                      </div>
                      <span v-if="kb.description" class="list-desc">{{ kb.description }}</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <AgentMarket
            v-else-if="showAgentMarket && !selectedMarketAgent"
            @close="showAgentMarket = false"
            @view-detail="onMarketViewDetail"
          />
          <div v-else-if="!selectedAgent && !selectedMarketAgent" class="no-selection">
            <p>{{ t('agentOption.selectAgentHint') }}</p>
          </div>

          <div v-else>
            <div class="agent-info" :class="{ 'is-readonly': !isEditing && !isCreating, 'is-editing': isEditing || isCreating }">
                <div class="agent-info-header">
                  <div class="name-wrapper">
                    <h3 v-if="!isEditing">{{ displayAgent?.name }}</h3>
                    <h3 v-else>{{ t('agentOption.editAgent') }}</h3>
                    <!-- 发布状态（仅我的创建）：私有 / 已发布 -->
                    <div v-if="!isEditing &amp;&amp; canEditSelectedAgent" class="publish-status-wrapper">
                      <span
                        class="publish-status-label"
                        :class="{
                          'status-private': !displayAgent?.public,
                          'status-published': displayAgent?.public
                        }"
                      >
                        {{ displayAgent?.public ? t('agentOption.published') : t('agentOption.private') }}
                      </span>
                    </div>
                    <button
                      v-if="!isEditing &amp;&amp; canShowSubscribeBtn &amp;&amp; !isDisplayAgentSubscribed"
                      class="subscribe-btn"
                      :disabled="subscribeLoading"
                      @click="handleSubscribe"
                    >
                      {{ subscribeLoading ? t('agentOption.subscribing') : t('agentOption.subscribe') }}
                    </button>
                    <button
                      v-if="!isEditing &amp;&amp; canShowSubscribeBtn &amp;&amp; isDisplayAgentSubscribed"
                      class="subscribe-btn unsubscribe"
                      :disabled="subscribeLoading"
                      @click="handleUnsubscribe"
                    >
                      {{ subscribeLoading ? t('agentOption.unsubscribing') : t('agentOption.unsubscribe') }}
                    </button>
                  </div>
                  <div class="agent-actions">
                    <template v-if="selectedMarketAgent">
                      <button class="action-btn back-to-market" @click="backToMarket">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                          <path d="M10 12L6 8l4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        {{ t('agentOption.backToSubscribe') }}
                      </button>
                    </template>
                    <template v-else-if="!isEditing &amp;&amp; canEditSelectedAgent">
                      <div class="agent-option-wrapper" ref="agentOptionMenuRef">
                        <button
                          class="agent-option-btn"
                          type="button"
                          @click.stop="toggleAgentOptionMenu"
                          :title="t('agentOption.agentOptions')"
                        >
                          <img src="@/assets/images/option_conversation.svg" width="18" height="18" alt="options" />
                        </button>
                        <div v-if="showAgentOptionMenu" class="agent-option-menu" :style="agentOptionMenuStyle">
                          <button class="agent-option-item" @click.stop="startEditFromMenu">
                            <img src="@/assets/images/edit_icon.svg" width="16" height="16" alt="edit" />
                            <span>{{ t('conversation.edit') }}</span>
                          </button>
                          <button
                            class="agent-option-item"
                            @click.stop="handlePublishFromMenu"
                          >
                          <img src="@/assets/images/lock.svg" width="16" height="16" alt="lock" />
                            <span>{{ selectedAgent?.public ? t('agentOption.stopPublish') : t('agentOption.publishToMarket') }}</span>
                          </button>
                          <button v-if="!selectedAgent?.public" class="agent-option-item agent-option-delete" @click.stop="handleDeleteFromMenu">
                            <img src="@/assets/images/delete.svg" width="16" height="16" alt="delete" />
                            <span>{{ t('common.delete') }}</span>
                          </button>
                        </div>
                      </div>
                    </template>
                    <template v-if="isEditing">
                      <button class="action-btn save-edit" @click="saveEdit">{{ t('common.save') }}</button>
                      <button class="action-btn cancel-edit" @click="cancelEdit">{{ t('common.cancel') }}</button>
                    </template>
                  </div>
                </div>
                <div class="agent-info-content">
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.model') }}<span class="required">*</span></label>
                    <div class="model-selector" ref="editModelSelectorRef">
                      <button class="model-select-btn" type="button" @click="toggleEditModelSelector">
                        <span>{{ editedSelectedModelDisplay }}</span>
                        <svg class="dropdown-icon" :class="{ 'rotate': showEditModelSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                          <path d="M6 8L2 4h8l-4 4z"/>
                        </svg>
                      </button>
                      <div class="model-dropdown" v-show="showEditModelSelector">
                        <div v-for="provider in modelProviders" :key="provider.model_source" class="model-group">
                          <div class="model-group-title">{{ provider.model_source }}</div>
                          <button 
                            v-for="model in provider.models" 
                            :key="model.id"
                            class="model-option"
                            :class="{ 'active': editedModel === model.id }"
                            type="button"
                            @click="selectEditModel(provider.model_source, model.id)"
                          >
                            {{ model.name }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="inline-fields" v-if="!isEditing">
                    <div class="field-group compact">
                      <label>{{ t('agentOption.model') }}</label>
                      <p>{{ displayAgent?.model_source || '-' }}: {{ displayAgent?.model || '-' }}</p>
                    </div>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.name') }}<span class="required">*</span></label>
                    <input v-model="editedName" class="edit-input-agent" :placeholder="t('agentOption.namePlaceholder')">
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.nameZh') }}</label>
                    <input v-model="editedNameZh" class="edit-input-agent" :placeholder="t('agentOption.nameZhPlaceholder')">
                  </div>
                  <div class="field-group" v-if="!isEditing">
                    <label>{{ t('agentOption.nameZh') }}</label>
                    <p>{{ displayAgent?.name_zh || t('messageInput.none') }}</p>
                  </div>
                  <div class="field-group">
                    <label>{{ t('agentOption.description') }}<span class="required" v-if="isEditing">*</span></label>
                    <p v-if="!isEditing">{{ displayAgent?.description }}</p>
                    <textarea v-else v-model="editedDescription" class="edit-textarea" :placeholder="t('agentOption.descriptionEditPlaceholder')"></textarea>
                  </div>
                  <div class="field-group">
                    <label>{{ t('agentOption.systemPrompt') }}<span class="required" v-if="isEditing">*</span></label>
                    <p v-if="!isEditing">{{ displayAgent?.system_prompt }}</p>
                    <textarea v-else v-model="editedSystemPrompt" class="edit-textarea" :placeholder="t('agentOption.systemPromptEditPlaceholder')"></textarea>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.historyInherit') }}</label>
                    <div class="history-toggle">
                      <div class="toggle-wrapper">
                        <label>{{ t('agentOption.mainAgentHistory') }}</label>
                        <div class="toggle" :class="{ active: editedSupervisorHistory }" @click="editedSupervisorHistory = !editedSupervisorHistory">
                          <div class="toggle-circle"></div>
                        </div>
                        <span class="toggle-comment">{{ t('agentOption.historyInheritHint') }}</span>
                      </div>
                    </div>
                  </div>
                <!-- 公告暂时隐藏 -->
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.fileLibrary') }}</label>
                    <div class="file-library-wrapper file-library-edit">
                      <div class="list-selection agent-file-list">
                        <button class="upload-file-btn-inline" type="button" @click="triggerEditFileUpload" :title="t('agentOption.addFile')">
                          <img src="@/assets/images/file_upload.svg" width="18" height="18" />
                          <span>{{ t('agentOption.addFile') }}</span>
                        </button>
                        <div class="file-item" v-for="(item) in editedAgentExistingFilesWithInfo" :key="'existing-' + item.file_id">
                          <span class="file-name">{{ item.name }}</span>
                          <button class="remove-file-btn-inline" type="button" @click.stop="removeExistingFile(item.file_id)" :title="t('common.delete')">
                            <img :src="DeleteFileIconUrl" :alt="t('common.delete')" />
                          </button>
                        </div>
                        <div class="file-item" v-for="(file, idx) in editedAgentNewFiles" :key="'new-' + getEditFileKey(file, idx)">
                          <span class="file-name">{{ file.name }}</span>
                          <button class="remove-file-btn-inline" type="button" @click.stop="removeEditNewFile(idx)" :title="t('common.delete')">
                            <img :src="DeleteFileIconUrl" :alt="t('common.delete')" />
                          </button>
                        </div>
                        <div v-if="editedAgentExistingFilesWithInfo.length === 0 && editedAgentNewFiles.length === 0" class="empty-docs">{{ t('agentOption.noFiles') }}</div>
                      </div>
                    </div>
                  </div>
                  <div class="field-group file-library-row" v-if="!isEditing && selectedAgentFilesDetail.length > 0">
                    <label>{{ t('agentOption.fileLibrary') }}</label>
                    <div class="file-library-wrapper">
                      <div class="list-selection agent-file-list">
                        <div
                          v-for="f in selectedAgentFilesDetail"
                          :key="f.file_id"
                          class="file-item"
                          :class="{ selected: selectedPreviewFile === f.name }"
                          @click="fetchAgentFileContent(f.name)"
                        >
                          <span class="file-name">{{ f.name }}</span>
                        </div>
                      </div>
                      <div class="file-preview-panel">
                        <div class="preview-header">
                          <h4>{{ selectedPreviewFile || t('agentOption.filePreview') }}</h4>
                          <div class="header-actions" v-if="selectedPreviewFile">
                            <img :src="DownloadIcon" :alt="t('kbOption.download')" class="icon-button" @click="downloadAgentFile(selectedPreviewFile)" />
                          </div>
                        </div>
                        <div class="preview-content">
                          <div v-if="!selectedPreviewFile" class="no-selection">
                            <p>{{ t('agentOption.selectFilePreview') }}</p>
                          </div>
                          <div v-else-if="previewError" class="error">{{ previewError }}</div>
                          <img v-else-if="isPreviewImage" :src="previewFileUrl" alt="Image Preview" class="preview-image" />
                          <iframe v-else-if="isPreviewHtml" :src="previewFileUrl" class="html-iframe" frameborder="0" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
                          <VueOfficeExcel v-else-if="isPreviewExcel" :src="previewFileUrl" />
                          <VueOfficePdf v-else-if="isPreviewPdf" :src="previewFileUrl" />
                          <VueOfficePptx v-else-if="isPreviewPpt" :src="previewFileUrl" />
                          <div v-else v-html="previewRenderContent"></div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="inline-fields" v-if="!isEditing">
                    <div class="field-group compact">
                      <label>{{ t('agentOption.tools') }}</label>
                      <ul v-if="selectedAgentToolsDetail.length" class="pill-list">
                        <li v-for="tool in selectedAgentToolsDetail" :key="tool.name" class="pill-item">
                          <span class="pill-title">{{ tool.name }}</span>
                          <span v-if="tool.description" class="pill-desc">{{ tool.description }}</span>
                        </li>
                      </ul>
                      <p v-else class="empty-text">{{ t('messageInput.none') }}</p>
                    </div>
                    <div class="field-group compact">
                      <label>{{ t('agentOption.skills') }}</label>
                      <div v-if="selectedAgentSkillsDetail.system.length || selectedAgentSkillsDetail.user.length" class="skill-readonly-wrap">
                        <div v-if="selectedAgentSkillsDetail.system.length" class="skill-readonly-block">
                          <span class="skill-readonly-type-label">{{ t('agentOption.systemSkills') }}</span>
                          <ul class="pill-list">
                            <li v-for="row in selectedAgentSkillsDetail.system" :key="'ro-sys-' + row.name" class="pill-item">
                              <span class="pill-title">{{ row.name }}</span>
                              <span v-if="row.description" class="pill-desc">{{ row.description }}</span>
                            </li>
                          </ul>
                        </div>
                        <div v-if="selectedAgentSkillsDetail.user.length" class="skill-readonly-block">
                          <span class="skill-readonly-type-label">{{ t('agentOption.personalSkills') }}</span>
                          <ul class="pill-list">
                            <li v-for="row in selectedAgentSkillsDetail.user" :key="'ro-user-' + row.name" class="pill-item">
                              <span class="pill-title">{{ row.name }}</span>
                              <span v-if="row.description" class="pill-desc">{{ row.description }}</span>
                            </li>
                          </ul>
                        </div>
                      </div>
                      <p v-else class="empty-text">{{ t('messageInput.none') }}</p>
                    </div>
                    <div class="field-group compact">
                      <label>{{ t('agentOption.knowledgeBase') }}</label>
                      <ul v-if="selectedAgentKbsDetail.length" class="pill-list">
                        <li v-for="kb in selectedAgentKbsDetail" :key="kb.name" class="pill-item">
                          <span class="pill-title">{{ kb.name }}</span>
                          <span v-if="kb.description" class="pill-desc">{{ kb.description }}</span>
                        </li>
                      </ul>
                      <p v-else class="empty-text">{{ t('messageInput.none') }}</p>
                    </div>
                    <div class="field-group compact">
                      <label>{{ t('agentOption.subAgents') }}</label>
                      <ul v-if="selectedAgentSubAgentsDetail.length" class="pill-list">
                        <li v-for="agent in selectedAgentSubAgentsDetail" :key="agent.agent_id || agent.name" class="pill-item">
                          <span class="pill-title">{{ agent.name }}</span>
                          <span v-if="agent.description" class="pill-desc">{{ agent.description }}</span>
                        </li>
                      </ul>
                      <p v-else class="empty-text">{{ t('messageInput.none') }}</p>
                    </div>
                  </div>
                  <div class="field-group" v-else>
                    <label>{{ t('agentOption.tools') }}</label>
                    <div class="list-selection">
                      <div 
                        v-for="(tools, classZh) in groupedTools" 
                        :key="classZh"
                        class="tool-group"
                      >
                        <!-- 分组头部 -->
                        <div class="tool-group-header" @click="toggleEditToolGroup(classZh)">
                          <div class="tool-group-header-text">
                            <span class="tool-group-name">{{ classZh }}</span>
                            <span class="tool-group-count">{{ t('agentOption.toolCount', { n: tools.length }) }}</span>
                            <span v-if="getSelectedCountInEditGroup(classZh) > 0" class="tool-group-selected">
                              {{ t('agentOption.selectedCount', { n: getSelectedCountInEditGroup(classZh) }) }}
                            </span>
                          </div>
                          <div class="tool-group-toggle">
                            <svg 
                              :class="['toggle-icon', { expanded: expandedEditToolGroups.includes(classZh) }]"
                              width="16" 
                              height="16" 
                              viewBox="0 0 16 16" 
                              fill="none"
                            >
                              <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                            </svg>
                          </div>
                        </div>
                        <!-- 分组下的工具列表 -->
                        <div v-if="expandedEditToolGroups.includes(classZh)" class="tool-group-items">
                          <label v-for="tool in tools" :key="tool.name" class="list-item">
                            <div class="list-item-header">
                              <input type="checkbox" :id="'edit-' + tool.name" :value="tool.name" v-model="selectedEditedTools" />
                              <span class="list-title">{{ tool.name }}</span>
                            </div>
                            <span v-if="tool.description" class="list-desc">{{ tool.description }}</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.skills') }}</label>
                    <div class="skill-agent-section">
                      <div class="skill-agent-subsection">
                        <div class="skill-agent-subtitle">{{ t('agentOption.systemSkills') }}</div>
                        <div v-if="systemSkillsList.length === 0" class="empty-state">{{ t('agentOption.noSystemSkills') }}</div>
                        <div v-else class="list-selection">
                          <label v-for="skill in systemSkillsList" :key="'edit-sys-' + skill.name" class="list-item">
                            <div class="list-item-header">
                              <input type="checkbox" :id="'edit-skill-sys-' + skill.name" :value="skill.name" v-model="selectedEditedSystemSkills" />
                              <span class="list-title">{{ skill.name }}</span>
                            </div>
                            <span v-if="skill.description" class="list-desc">{{ skill.description }}</span>
                          </label>
                        </div>
                      </div>
                      <div class="skill-agent-subsection">
                        <div class="skill-agent-subtitle">{{ t('agentOption.personalSkills') }}</div>
                        <div v-if="userSkillsList.length === 0" class="empty-state">{{ t('agentOption.noPersonalSkills') }}</div>
                        <div v-else class="list-selection">
                          <label v-for="skill in userSkillsList" :key="'edit-user-' + skill.name" class="list-item">
                            <div class="list-item-header">
                              <input type="checkbox" :id="'edit-skill-user-' + skill.name" :value="skill.name" v-model="selectedEditedUserSkills" />
                              <span class="list-title">{{ skill.name }}</span>
                            </div>
                            <span v-if="skill.description" class="list-desc">{{ skill.description }}</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.subAgents') }}</label>
                    <div v-if="filteredSubAgents.length === 0" class="empty-state">{{ t('agentOption.noSubAgents') }}</div>
                    <div v-else class="list-selection">
                      <label v-for="agent in filteredSubAgents" :key="agent.agent_id" class="list-item">
                        <div class="list-item-header">
                          <input type="checkbox" :id="'edit-sub-' + agent.agent_id" :value="agent.agent_id" v-model="selectedEditedSubAgents" />
                          <span class="list-title">{{ agent.name }}</span>
                        </div>
                        <span v-if="agent.description" class="list-desc">{{ agent.description }}</span>
                      </label>
                    </div>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>{{ t('agentOption.knowledgeBase') }}</label>
                    <div class="list-selection">
                      <label v-for="kb in allKbs" :key="kb.kb_id" class="list-item">
                        <div class="list-item-header">
                          <input type="checkbox" :id="'edit-kb-' + kb.kb_id" :value="kb.kb_id" v-model="selectedEditedKbs" />
                          <span class="list-title">{{ kb.name }}</span>
                        </div>
                        <span v-if="kb.description" class="list-desc">{{ kb.description }}</span>
                      </label>
                    </div>
                  </div>
                </div>
            </div>
          </div>
        </div>
      </div>

      <input type="file" multiple ref="newFileInput" style="display: none;" @change="handleNewFileUpload" />
      <input type="file" multiple ref="editFileInput" style="display: none;" @change="handleEditFileUpload" />

      <!-- 取消发布确认模态 -->
      <div v-if="showUnpublishConfirmModal" class="confirm-modal">
        <div class="confirm-content">
          <h3>{{ t('agentOption.confirmUnpublishTitle') }}</h3>
          <p>{{ t('agentOption.confirmUnpublishMessage') }}</p>
          <div class="confirm-buttons">
            <button class="confirm-btn" @click="confirmUnpublish">{{ t('common.confirm') }}</button>
            <button class="cancel-btn" @click="showUnpublishConfirmModal = false">{{ t('common.cancel') }}</button>
          </div>
        </div>
      </div>

      <!-- 删除确认模态 -->
      <div v-if="showConfirmModal" class="confirm-modal">
        <div class="confirm-content">
          <h3>{{ t('kbOption.confirmDelete') }}</h3>
          <p>{{ confirmMessage }}</p>
          <div class="confirm-buttons">
            <button class="confirm-btn" @click="confirmDelete">{{ t('common.confirm') }}</button>
            <button class="cancel-btn" @click="cancelConfirm">{{ t('common.cancel') }}</button>
          </div>
        </div>
      </div>

      <!-- 错误模态 -->
      <div v-if="showErrorModal" class="error-modal">
        <div class="error-content">
          <h3><img src="@/assets/images/error_icon.svg" width="18" height="18" :alt="t('agentOption.errorTitle')" /> {{ t('agentOption.errorTitle') }}</h3>
          <p>{{ errorMessage }}</p>
          <div class="confirm-buttons">
            <button class="ok-btn" @click="showErrorModal = false">{{ t('agentOption.ok') }}</button>
          </div>
        </div>
      </div>

      <!-- 发布结果模态 -->
      <div v-if="showPublishResultModal" class="error-modal">
        <div class="error-content publish-result-content">
          <p>{{ publishResultMessage }}</p>
          <div class="confirm-buttons">
            <button class="ok-btn" @click="showPublishResultModal = false">{{ t('agentOption.ok') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
// @ts-ignore
import DownloadIcon from '@/assets/images/download_icon.svg?url'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/excel/lib/index.css'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficePptx from '@vue-office/pptx'
import mammoth from 'mammoth'
import AgentMarket from './AgentMarket.vue'

defineEmits<{ close: [] }>()
const { userId, username } = defineProps<{ userId: string; username?: string }>()

// 接口定义
interface AgentFile {
  file_id: string
  name: string
}

interface Agent {
  agent_id: string
  name: string
  name_zh?: string  // 智能体中文名称
  description: string
  system_prompt: string
  tools: string[]
  skills?: { system?: string[]; user?: string[] } | null
  kbs: string[]
  files?: AgentFile[]
  announcement?: string
  create_at?: string
  updated_at?: string
  agents?: string[] | null
  supervisor_history?: boolean
  self_history?: boolean
  user_id: string
  user_name?: string  // 创建者用户名，前端从 Chat 传入
  public?: boolean   // 是否公开，默认 false
  model_source?: string
  model?: string
}

interface ToolItem {
  name: string
  description?: string
  class_zh?: string
}

/** 与 /api/skills_info 及后端 AgentCard.skills 对齐：个人侧存为 user */
interface SkillItem {
  name: string
  description: string
  type: 'system' | 'user'
}

function normalizeAgentSkills(raw: unknown): { system: string[]; user: string[] } | null {
  if (raw == null || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const system = Array.isArray(o.system) ? (o.system as string[]).filter(Boolean) : []
  const user = Array.isArray(o.user) ? (o.user as string[]).filter(Boolean) : []
  if (!system.length && !user.length) return null
  return { system, user }
}

function serializeSkillsPayload(
  systemNames: string[],
  userNames: string[]
): { system: string[]; user: string[] } | null {
  const system = [...systemNames].filter(Boolean)
  const user = [...userNames].filter(Boolean)
  if (!system.length && !user.length) return null
  return { system, user }
}

const agentList = ref<Agent[]>([])
const selectedAgent = ref<Agent | null>(null)
const selectedMarketAgent = ref<Agent | null>(null)
const marketAgentsForLookup = ref<Agent[]>([])
const showAgentMarket = ref(false)

// 用于详情展示的智能体：市场选中优先，否则为侧边栏选中
const displayAgent = computed(() => selectedMarketAgent.value ?? selectedAgent.value)

// 合并 agentList 与市场智能体，用于子智能体名称解析
const mergedAgentListForLookup = computed(() => [
  ...agentList.value,
  ...(marketAgentsForLookup.value || [])
])
const loading = ref(false)
const error = ref('')
const isEditing = ref(false)
const editedName = ref('')
const editedNameZh = ref('')
const editedDescription = ref('')
const editedSystemPrompt = ref('')
const editedAnnouncement = ref('')
const editedTools = ref('')
const editedKbs = ref('')

const isCreating = ref(false)
const newName = ref('')
const newNameZh = ref('')
const newDescription = ref('')
const newSystemPrompt = ref('')
const newAnnouncement = ref('')

const showConfirmModal = ref(false)
const showUnpublishConfirmModal = ref(false)
const confirmMessage = ref('')
const currentAgentIdForDelete = ref('')

const showErrorModal = ref(false)
const errorMessage = ref('')

// 发布状态相关
const publishLoading = ref(false)
const showPublishResultModal = ref(false)
const publishResultMessage = ref('')

// 智能体选项菜单（仿 conversation 编辑/删除）
const showAgentOptionMenu = ref(false)
const agentOptionMenuRef = ref<HTMLElement | null>(null)
const agentOptionMenuStyle = ref<{ top: string; left: string }>({ top: '0px', left: '0px' })

const allTools = ref<ToolItem[]>([])
/** 创建专家时默认勾选的工具名（来自 /api/agent_default_tools，仅预填，用户可取消） */
const defaultNewAgentTools = ref<string[]>([])
const allSkills = ref<SkillItem[]>([])
const selectedNewTools = ref<string[]>([])
const selectedEditedTools = ref<string[]>([])
const selectedNewSystemSkills = ref<string[]>([])
const selectedNewUserSkills = ref<string[]>([])
const selectedEditedSystemSkills = ref<string[]>([])
const selectedEditedUserSkills = ref<string[]>([])
const selectedNewSubAgents = ref<string[]>([])
const selectedEditedSubAgents = ref<string[]>([])

// 工具分组折叠状态
const expandedToolGroups = ref<string[]>([])
const expandedEditToolGroups = ref<string[]>([])

// Add new refs for kbs
const allKbs = ref<{kb_id: string, name: string, description?: string}[]>([])
const selectedNewKbs = ref<string[]>([])
const selectedEditedKbs = ref<string[]>([])

// Add new refs for history inheritance
const newSupervisorHistory = ref(true)
const newSelfHistory = ref(false)
const editedSupervisorHistory = ref(true)
const editedSelfHistory = ref(false)

// 文件库相关
const newAgentFiles = ref<File[]>([])
const editedAgentNewFiles = ref<File[]>([])
const agentFilesToDelete = ref<string[]>([])
const newFileInput = ref<HTMLInputElement | null>(null)
const editFileInput = ref<HTMLInputElement | null>(null)
const newFilePreviewUrls = ref(new Map<string, string>())
const editFilePreviewUrls = ref(new Map<string, string>())

const DeleteFileIconUrl = new URL('@/assets/images/delete_file.svg', import.meta.url).href
const DocIconUrl = new URL('@/assets/images/doc_update.svg', import.meta.url).href
const ExcelIconUrl = new URL('@/assets/images/excel_update.svg', import.meta.url).href
const PptIconUrl = new URL('@/assets/images/ppt_update.svg', import.meta.url).href
const PdfIconUrl = new URL('@/assets/images/pdf_update.svg', import.meta.url).href
const FileIconUrl = new URL('@/assets/images/file_update.svg', import.meta.url).href

// 文件预览相关（仅 readonly 模式）
const selectedPreviewFile = ref<string | null>(null)
const previewFileContent = ref<string>('')
const previewError = ref<string>('')
const previewFileUrl = ref<string>('')
const previewFileBlob = ref<Blob | null>(null)

const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (_) {}
    }
    return ''
  }
})

const selectedAgentKbsDetail = computed(() => {
  const agent = displayAgent.value
  if (!agent?.kbs) return []
  return agent.kbs.map((id: string) => {
    const kb = allKbs.value.find(k => k.kb_id === id)
    return {
      name: kb?.name || id,
      description: kb?.description || ''
    }
  })
})

const toolDescriptionMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  allTools.value.forEach(tool => {
    map[tool.name] = tool.description || ''
  })
  return map
})

const skillDescriptionMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  allSkills.value.forEach(skill => {
    map[skill.name] = skill.description || ''
  })
  return map
})

const systemSkillsList = computed(() => allSkills.value.filter(s => s.type === 'system'))
const userSkillsList = computed(() => allSkills.value.filter(s => s.type === 'user'))

const selectedAgentSkillsDetail = computed(() => {
  const agent = displayAgent.value
  const empty = {
    system: [] as { name: string; description: string }[],
    user: [] as { name: string; description: string }[]
  }
  const raw = agent?.skills
  if (!raw) return empty
  const mapRow = (name: string) => ({
    name,
    description: skillDescriptionMap.value[name] || ''
  })
  return {
    system: (raw.system || []).map(mapRow),
    user: (raw.user || []).map(mapRow)
  }
})

const selectedAgentToolsDetail = computed(() => {
  const agent = displayAgent.value
  if (!agent?.tools) return []
  return agent.tools.map((name: string) => ({
    name,
    description: toolDescriptionMap.value[name] || ''
  }))
})

const agentDescriptionMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  mergedAgentListForLookup.value.forEach((agent: Agent) => {
    map[agent.agent_id] = agent.description || ''
    map[agent.name] = agent.description || ''
  })
  return map
})

// 子智能体详情：agents 保存 agent_id，根据 id 从 mergedAgentListForLookup 查找名称与描述
const selectedAgentSubAgentsDetail = computed(() => {
  const agent = displayAgent.value
  if (!agent?.agents || agent.agents.length === 0) return []
  return agent.agents.map((idOrName: string) => {
    const a = mergedAgentListForLookup.value.find((x: Agent) => x.agent_id === idOrName || x.name === idOrName)
    return {
      agent_id: a?.agent_id || idOrName,
      name: a?.name_zh || a?.name || idOrName,
      description: a?.description || agentDescriptionMap.value[idOrName] || ''
    }
  })
})

const selectedAgentFilesDetail = computed(() => {
  const agent = displayAgent.value
  if (!agent?.files) return []
  return agent.files.filter((f: AgentFile) => !agentFilesToDelete.value.includes(f.file_id))
})

const editedAgentExistingFilesWithInfo = computed(() => {
  if (!selectedAgent.value?.files) return []
  return selectedAgent.value.files.filter(f => !agentFilesToDelete.value.includes(f.file_id))
})

// 文件预览 computed
const previewFileExtension = computed(() =>
  selectedPreviewFile.value?.split('.').pop()?.toLowerCase() || ''
)
const isPreviewImage = computed(() => ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(previewFileExtension.value))
const isPreviewHtml = computed(() => selectedPreviewFile.value?.endsWith('.html'))
const isPreviewDocx = computed(() => ['doc', 'docx'].includes(previewFileExtension.value))
const isPreviewExcel = computed(() => ['xls', 'xlsx', 'csv'].includes(previewFileExtension.value))
const isPreviewPdf = computed(() => previewFileExtension.value === 'pdf')
const isPreviewPpt = computed(() => ['ppt', 'pptx'].includes(previewFileExtension.value))
const isPreviewTextFile = computed(() =>
  ['txt', 'md', 'json', 'csv'].includes(previewFileExtension.value) ||
  (!isPreviewImage.value && !isPreviewHtml.value && !isPreviewDocx.value && !isPreviewExcel.value && !isPreviewPdf.value && !isPreviewPpt.value)
)
const previewRenderContent = computed(() => {
  if (isPreviewDocx.value) return previewFileContent.value
  if (!previewFileContent.value || !isPreviewTextFile.value) return ''
  return md.render(previewFileContent.value)
})

// Filter out invalid/empty agents to prevent blank items
const filteredAgentList = computed(() => {
  return agentList.value.filter(agent => agent.agent_id && agent.name?.trim())
})

// 按 user_id 分组的智能体：我的创建 / 我的订阅 / 系统预设
const myCreatedAgents = computed(() =>
  filteredAgentList.value.filter(a => a.user_id === userId)
)
const mySubscribedAgents = computed(() =>
  filteredAgentList.value.filter(a => a.user_id !== userId && a.user_id !== 'mengya')
)
const systemPresetAgents = computed(() =>
  filteredAgentList.value.filter(a => a.user_id === 'mengya')
)

// 各块下拉栏展开状态
const expandedBlocks = ref<Record<string, boolean>>({
  myCreated: true,   // 默认展开
  mySubscribed: false,
  systemPreset: false
})
const toggleBlock = (key: string) => {
  expandedBlocks.value[key] = !expandedBlocks.value[key]
}

// 仅「我的创建」可编辑，我的订阅和系统预设隐藏编辑/删除按钮
const canEditSelectedAgent = computed(() => {
  const agent = selectedAgent.value
  if (!agent) return false
  return agent.user_id === userId && agent.user_id !== 'mengya'
})

// 当前展示的智能体是否已订阅
const isDisplayAgentSubscribed = computed(() => {
  const agent = displayAgent.value
  if (!agent?.agent_id) return false
  return mySubscribedAgents.value.some(a => a.agent_id === agent.agent_id)
})

// 是否显示订阅/取消订阅按钮（非自己的智能体才显示，不能订阅自己的；系统预设不允许订阅）
const canShowSubscribeBtn = computed(() => {
  const agent = displayAgent.value
  if (!agent?.agent_id || canEditSelectedAgent.value || agent.user_id === userId) return false
  if (agent.user_id === 'mengya') return false  // 系统预设不允许订阅
  return true
})

const subscribeLoading = ref(false)

const filteredSubAgents = computed(() => {
  let agents = filteredAgentList.value;
  if (isEditing && selectedAgent.value) {
    agents = agents.filter(agent => agent.agent_id !== selectedAgent.value!.agent_id);
  }
  return agents;
})

// 工具按 class_zh 分组
const groupedTools = computed(() => {
  const groups: Record<string, ToolItem[]> = {}
  allTools.value.forEach(tool => {
    const classZh = tool.class_zh || t('common.uncategorized')
    if (!groups[classZh]) {
      groups[classZh] = []
    }
    groups[classZh].push(tool)
  })
  return groups
})

// 切换工具分组展开/收起（创建）
const toggleToolGroup = (classZh: string) => {
  const index = expandedToolGroups.value.indexOf(classZh)
  if (index > -1) {
    expandedToolGroups.value.splice(index, 1)
  } else {
    expandedToolGroups.value.push(classZh)
  }
}

// 切换工具分组展开/收起（编辑）
const toggleEditToolGroup = (classZh: string) => {
  const index = expandedEditToolGroups.value.indexOf(classZh)
  if (index > -1) {
    expandedEditToolGroups.value.splice(index, 1)
  } else {
    expandedEditToolGroups.value.push(classZh)
  }
}

// 计算每个分组中已选择的工具数量（创建）
const getSelectedCountInGroup = (classZh: string) => {
  const tools = groupedTools.value[classZh] || []
  return tools.filter(tool => selectedNewTools.value.includes(tool.name)).length
}

// 计算每个分组中已选择的工具数量（编辑）
const getSelectedCountInEditGroup = (classZh: string) => {
  const tools = groupedTools.value[classZh] || []
  return tools.filter(tool => selectedEditedTools.value.includes(tool.name)).length
}

async function fetchAgentList() {
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`/api/agent_cards/${userId}`)
    console.log(response.data)
    agentList.value = response.data.map((item: any) => ({
      ...item,
      tools: item.tools || [],
      skills: normalizeAgentSkills(item.skills),
      kbs: item.kbs || [],
      files: item.files || [],
      agents: item.agents || null,
      supervisor_history: item.supervisor_history ?? true,
      self_history: item.self_history ?? true,
      public: item.public ?? false
    })) // Ensure arrays are initialized
    // 如果有选中的，更新它
    if (selectedAgent.value) {
      const updated = agentList.value.find(a => a.agent_id === selectedAgent.value!.agent_id)
      if (updated) selectedAgent.value = updated
    }
  } catch (err) {
    error.value = 'Failed to load agents'
  } finally {
    loading.value = false
  }
}

async function fetchTools() {
  try {
    const response = await axios.get('/api/tools_info')
    allTools.value = response.data.map((tool: any) => ({
      name: tool.name,
      description: tool.description || '',
      class_zh: tool.class_zh || t('common.uncategorized')
    }))
  } catch (err) {
    console.error('Failed to fetch tools:', err)
  }
}

function pickDefaultToolsForNewAgent(): string[] {
  const valid = new Set(allTools.value.map(t => t.name))
  return defaultNewAgentTools.value.filter(n => valid.has(n))
}

async function fetchDefaultNewAgentTools() {
  try {
    const response = await axios.get('/api/agent_default_tools')
    const raw = response.data as unknown
    if (
      raw &&
      typeof raw === 'object' &&
      'success' in raw &&
      (raw as { success?: boolean }).success === false
    ) {
      defaultNewAgentTools.value = []
      return
    }
    const names = Array.isArray(raw)
      ? raw
      : (raw as { tool_names?: string[] })?.tool_names
    defaultNewAgentTools.value = Array.isArray(names)
      ? names.filter((n): n is string => typeof n === 'string' && n.length > 0)
      : []
  } catch (err) {
    console.error('Failed to fetch default agent tools:', err)
    defaultNewAgentTools.value = []
  }
}

function mapSkillApiType(raw: unknown): 'system' | 'user' {
  if (raw === 'user' || raw === 'personal') return 'user'
  return 'system'
}

async function fetchSkills() {
  try {
    const response = await axios.get('/api/skills_info')
    const apiList = Array.isArray(response.data) ? response.data : []
    allSkills.value = apiList.map((skill: any) => ({
      name: skill.name,
      description: skill.description || '',
      type: skill.type != null ? mapSkillApiType(skill.type) : 'system'
    }))
  } catch (err) {
    console.error('Failed to fetch skills:', err)
  }
}

// Add fetchKbs function
async function fetchKbs() {
  try {
    const response = await axios.get(`/kb/kb/list/?user_id=${userId}`)
    if (response.data.success) {
      allKbs.value = response.data.data.map((kb: any) => ({
        kb_id: kb.kb_id,
        name: kb.kb_name_zh,
        description: kb.kb_description || kb.kb_desc || kb.description || ''
      }))
    }
  } catch (err) {
    console.error('Failed to fetch kbs:', err)
  }
}

const model_list = ref<Record<string, string[]>>({})

// Fetch models
async function fetchModels() {
  try {
    const response = await axios.get('/api/message/models')
    model_list.value = response.data
  } catch (error) {
    console.error('Failed to fetch models:', error)
  }
}

function selectAgent(agent: Agent) {
  selectedAgent.value = agent
  selectedMarketAgent.value = null
  isEditing.value = false
  isCreating.value = false
  showAgentMarket.value = false
  selectedPreviewFile.value = null
}

function openAgentMarket() {
  showAgentMarket.value = true
  selectedAgent.value = null
  selectedMarketAgent.value = null
  isCreating.value = false
}

function onMarketViewDetail(agent: unknown, marketAgents: unknown) {
  selectedMarketAgent.value = agent as Agent
  marketAgentsForLookup.value = (Array.isArray(marketAgents) ? marketAgents : []) as Agent[]
  selectedPreviewFile.value = null
}

function backToMarket() {
  selectedMarketAgent.value = null
  marketAgentsForLookup.value = []
  selectedPreviewFile.value = null
}

async function handleSubscribe() {
  const agent = displayAgent.value
  if (!agent?.agent_id || subscribeLoading.value) return
  subscribeLoading.value = true
  try {
    const res = await axios.post(
      `/api/agent_subscription/${userId}/update`,
      null,
      { params: { agent_id: agent.agent_id } }
    )
    if (res.data?.success) {
      await fetchAgentList()
    } else {
      errorMessage.value = res.data?.message || t('agentOption.subscribeFailed')
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = t('agentOption.subscribeFailed') + ': ' + (err as Error).message
    showErrorModal.value = true
  } finally {
    subscribeLoading.value = false
  }
}

async function handleUnsubscribe() {
  const agent = displayAgent.value
  if (!agent?.agent_id || subscribeLoading.value) return
  subscribeLoading.value = true
  try {
    const res = await axios.delete(
      `/api/agent_subscription/${userId}/delete`,
      { params: { agent_id: agent.agent_id } }
    )
    if (res.data?.success) {
      await fetchAgentList()
      if (selectedMarketAgent.value?.agent_id === agent.agent_id) {
        selectedMarketAgent.value = null
      }
      if (selectedAgent.value?.agent_id === agent.agent_id) {
        selectedAgent.value = null
      }
    } else {
      errorMessage.value = res.data?.message || t('agentOption.unsubscribeFailed')
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = t('agentOption.unsubscribeFailed') + ': ' + (err as Error).message
    showErrorModal.value = true
  } finally {
    subscribeLoading.value = false
  }
}

function startCreate() {
  selectedAgent.value = null
  isCreating.value = true
  // Reset new agent fields
  newName.value = ''
  newNameZh.value = ''
  newDescription.value = ''
  newSystemPrompt.value = ''
  newAnnouncement.value = ''
  selectedNewTools.value = pickDefaultToolsForNewAgent()
  selectedNewSystemSkills.value = []
  selectedNewUserSkills.value = []
  selectedNewSubAgents.value = []
  selectedNewKbs.value = []
  newSupervisorHistory.value = true
  newSelfHistory.value = false
  newAgentFiles.value = []
  clearNewFilePreviews()
  expandedToolGroups.value = []
}

async function confirmCreate() {
  if (!newName.value.trim()) {
    errorMessage.value = t('agentOption.nameRequired')
    showErrorModal.value = true
    return
  }
  if (!newDescription.value.trim()) {
    errorMessage.value = t('agentOption.descriptionRequired')
    showErrorModal.value = true
    return
  }
  if (!newModel.value) {
    errorMessage.value = t('agentOption.modelRequired')
    showErrorModal.value = true
    return
  }
  const newAgent = {
    user_id: userId,
    user_name: username || '',
    agent_id: "",
    name: newName.value,
    name_zh: newNameZh.value.trim() || undefined,
    description: newDescription.value,
    system_prompt: newSystemPrompt.value,
    tools: selectedNewTools.value,
    skills: serializeSkillsPayload(selectedNewSystemSkills.value, selectedNewUserSkills.value),
    agents: selectedNewSubAgents.value.length > 0 ? selectedNewSubAgents.value : null,
    kbs: selectedNewKbs.value,
    announcement: '',
    supervisor_history: newSupervisorHistory.value,
    self_history: newSelfHistory.value,
    model_source: newModelSource.value,
    model: newModel.value
  }
  try {
    let response
    if (newAgentFiles.value.length > 0) {
      const formData = new FormData()
      formData.append('data', JSON.stringify(newAgent))
      newAgentFiles.value.forEach(file => formData.append('files', file))
      response = await axios.post('/api/agent_card/create', formData)
    } else {
      response = await axios.post('/api/agent_card/create', newAgent)
    }
    if (response.data.success) {
      await fetchAgentList()
      isCreating.value = false
      newAgentFiles.value = []
      clearNewFilePreviews()
      // Optionally select the new agent
      const createdAgent = agentList.value.find(a => a.name === newName.value)
      if (createdAgent) selectAgent(createdAgent)
    } else {
      errorMessage.value = response.data.message || t('agentOption.createFailed')
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = t('agentOption.createFailed') + ': ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelCreate() {
  isCreating.value = false
  newAgentFiles.value = []
  clearNewFilePreviews()
  expandedToolGroups.value = []
}

async function deleteAgent(agentId: string) {
  confirmMessage.value = t('agentOption.confirmDeleteAgent')
  currentAgentIdForDelete.value = agentId
  showConfirmModal.value = true
}

async function confirmDelete() {
  showConfirmModal.value = false
  try {
    await axios.post(`/api/agent_card/${currentAgentIdForDelete.value}/delete`)
    fetchAgentList()
    if (selectedAgent.value?.agent_id === currentAgentIdForDelete.value) {
      selectedAgent.value = null
    }
  } catch (err) {
    errorMessage.value = t('agentOption.deleteFailed') + ': ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelConfirm() {
  showConfirmModal.value = false
}

async function handlePublishClick(publicVal: boolean) {
  if (!selectedAgent.value) return
  publishLoading.value = true
  showPublishResultModal.value = true
  publishResultMessage.value = t('agentOption.reviewing')
  try {
    const response = await axios.post(
      `/api/agent_card/${selectedAgent.value.agent_id}/public`,
      null,
      { params: { public: publicVal } }
    )
    const data = response.data
    if (data && typeof data.success === 'boolean') {
      if (data.success) {
        publishResultMessage.value = t('agentOption.success')
        if (selectedAgent.value) selectedAgent.value.public = publicVal
        const index = agentList.value.findIndex(a => a.agent_id === selectedAgent.value!.agent_id)
        if (index !== -1) agentList.value[index] = { ...agentList.value[index], public: publicVal }
      } else {
        publishResultMessage.value = data.content || t('agentOption.operationFailed')
      }
    } else {
      publishResultMessage.value = t('agentOption.reviewing')
    }
  } catch {
    publishResultMessage.value = t('agentOption.requestFailed')
  } finally {
    publishLoading.value = false
  }
}


function toggleAgentOptionMenu() {
  if (showAgentOptionMenu.value) {
    showAgentOptionMenu.value = false
    return
  }
  showAgentOptionMenu.value = true
  nextTick(() => {
    const btn = agentOptionMenuRef.value?.querySelector('.agent-option-btn')
    const rect = btn?.getBoundingClientRect()
    if (rect) {
      agentOptionMenuStyle.value = {
        top: `${rect.bottom + 6}px`,
        left: `${rect.left}px`
      }
    }
  })
}

function startEditFromMenu() {
  showAgentOptionMenu.value = false
  startEdit()
}

function handleDeleteFromMenu() {
  showAgentOptionMenu.value = false
  if (selectedAgent.value) deleteAgent(selectedAgent.value.agent_id)
}

function handlePublishFromMenu() {
  showAgentOptionMenu.value = false
  if (!selectedAgent.value) return
  if (selectedAgent.value.public) {
    showUnpublishConfirmModal.value = true
  } else {
    handlePublishClick(true)
  }
}

async function confirmUnpublish() {
  showUnpublishConfirmModal.value = false
  if (selectedAgent.value) await handlePublishClick(false)
}

function handleAgentOptionMenuClickOutside(event: Event) {
  if (agentOptionMenuRef.value && !agentOptionMenuRef.value.contains(event.target as Node)) {
    showAgentOptionMenu.value = false
  }
}

function startEdit() {
  selectedPreviewFile.value = null
  if (selectedAgent.value) {
    editedName.value = selectedAgent.value.name
    editedNameZh.value = selectedAgent.value.name_zh || ''
    editedDescription.value = selectedAgent.value.description
    editedSystemPrompt.value = selectedAgent.value.system_prompt
    editedAnnouncement.value = ''
    selectedEditedTools.value = [...(selectedAgent.value.tools || [])]
    selectedEditedSystemSkills.value = [...(selectedAgent.value.skills?.system || [])]
    selectedEditedUserSkills.value = [...(selectedAgent.value.skills?.user || [])]
    // 将 agents 转为 agent_id 数组（兼容旧数据中的 agent_name）
    selectedEditedSubAgents.value = (selectedAgent.value.agents || []).map(idOrName => {
      const agent = agentList.value.find(a => a.agent_id === idOrName || a.name === idOrName)
      return agent?.agent_id || idOrName
    }).filter(Boolean)
    selectedEditedKbs.value = [...(selectedAgent.value.kbs || [])]
    editedSupervisorHistory.value = selectedAgent.value.supervisor_history ?? true
    editedSelfHistory.value = selectedAgent.value.self_history ?? false
    editedModelSource.value = selectedAgent.value.model_source || ''
    editedModel.value = selectedAgent.value.model || ''
    editedAgentNewFiles.value = []
    agentFilesToDelete.value = []
    clearEditFilePreviews()
    expandedEditToolGroups.value = []
    isEditing.value = true
  }
}

async function saveEdit() {
  if (!selectedAgent.value) return
  if (!editedName.value.trim()) {
    errorMessage.value = t('agentOption.nameRequired')
    showErrorModal.value = true
    return
  }
  if (!editedDescription.value.trim()) {
    errorMessage.value = t('agentOption.descriptionRequired')
    showErrorModal.value = true
    return
  }
  if (!editedModel.value) {
    errorMessage.value = t('agentOption.modelRequired')
    showErrorModal.value = true
    return
  }
  try {
    const updatedAgent = {
      user_id: userId,
      user_name: username || '',
      agent_id: selectedAgent.value.agent_id,
      name: editedName.value,
      name_zh: editedNameZh.value.trim() || undefined,
      description: editedDescription.value,
      system_prompt: editedSystemPrompt.value,
      announcement: '',
      tools: selectedEditedTools.value,
      skills: serializeSkillsPayload(selectedEditedSystemSkills.value, selectedEditedUserSkills.value),
      agents: selectedEditedSubAgents.value.length > 0 ? selectedEditedSubAgents.value : null,
      kbs: selectedEditedKbs.value,
      supervisor_history: editedSupervisorHistory.value,
      self_history: editedSelfHistory.value,
      model_source: editedModelSource.value,
      model: editedModel.value,
      files_to_delete: agentFilesToDelete.value
    }
    let response
    if (editedAgentNewFiles.value.length > 0 || agentFilesToDelete.value.length > 0) {
      const formData = new FormData()
      formData.append('data', JSON.stringify(updatedAgent))
      editedAgentNewFiles.value.forEach(file => formData.append('files', file))
      response = await axios.post(`/api/agent_card/${selectedAgent.value.agent_id}/update`, formData)
    } else {
      response = await axios.post(`/api/agent_card/${selectedAgent.value.agent_id}/update`, updatedAgent)
    }
    if (response.data.success) {
      const updatedFiles = response.data.files ?? selectedAgent.value.files?.filter(f => !agentFilesToDelete.value.includes(f.file_id)) ?? []
      Object.assign(selectedAgent.value, {
        ...updatedAgent,
        files: updatedFiles,
        skills: normalizeAgentSkills(updatedAgent.skills)
      })
      const index = agentList.value.findIndex(a => a.agent_id === selectedAgent.value!.agent_id)
      if (index !== -1) {
        agentList.value[index] = { ...agentList.value[index], ...selectedAgent.value }
      }
      editedAgentNewFiles.value = []
      agentFilesToDelete.value = []
      clearEditFilePreviews()
      isEditing.value = false
      await fetchAgentList()
    } else {
      errorMessage.value = response.data.message || t('agentOption.updateFailed')
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = t('agentOption.updateFailed') + ': ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelEdit() {
  isEditing.value = false
  editedName.value = ''
  editedNameZh.value = ''
  editedDescription.value = ''
  editedSystemPrompt.value = ''
  editedAnnouncement.value = ''
  selectedEditedTools.value = []
  selectedEditedSystemSkills.value = []
  selectedEditedUserSkills.value = []
  selectedEditedSubAgents.value = []
  selectedEditedKbs.value = []
  editedSupervisorHistory.value = true
  editedSelfHistory.value = false
  editedAgentNewFiles.value = []
  agentFilesToDelete.value = []
  clearEditFilePreviews()
  expandedEditToolGroups.value = []
}

function handleOverlayClick() {
  // 点击遮罩关闭
}

onMounted(async () => {
  if (userId) void fetchAgentList()
  await Promise.all([
    fetchTools(),
    fetchSkills(),
    fetchKbs(),
    fetchModels(),
    fetchDefaultNewAgentTools()
  ])
  document.addEventListener('click', handleNewModelClickOutside)
  document.addEventListener('click', handleEditModelClickOutside)
  document.addEventListener('click', handleAgentOptionMenuClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleNewModelClickOutside)
  document.removeEventListener('click', handleEditModelClickOutside)
  document.removeEventListener('click', handleAgentOptionMenuClickOutside)
  clearNewFilePreviews()
  clearEditFilePreviews()
})

// Model providers computed
const modelProviders = computed(() => {
  return Object.entries(model_list.value).map(([providerName, models]) => ({
    model_source: providerName,
    models: models.map(model => ({
      id: model,
      name: model
    })),
  }))
})

// For new agent
const showNewModelSelector = ref(false)
const newModelSelectorRef = ref<HTMLElement>()
const newModelSource = ref('')
const newModel = ref('')

const newSelectedModelDisplay = computed(() => {
  if (!newModel.value) return t('agentOption.selectModel')
  for (const provider of modelProviders.value) {
    const model = provider.models.find(m => m.id === newModel.value)
    if (model) return model.name
  }
  return t('agentOption.selectModel')
})

function toggleNewModelSelector() {
  showNewModelSelector.value = !showNewModelSelector.value
}

function selectNewModel(model_source: string, model: string) {
  newModelSource.value = model_source
  newModel.value = model
  showNewModelSelector.value = false
}

function handleNewModelClickOutside(event: Event) {
  if (newModelSelectorRef.value && !newModelSelectorRef.value.contains(event.target as Node)) {
    showNewModelSelector.value = false
  }
}

// For edit
const showEditModelSelector = ref(false)
const editModelSelectorRef = ref<HTMLElement>()
const editedModelSource = ref('')
const editedModel = ref('')

const editedSelectedModelDisplay = computed(() => {
  if (!editedModel.value) return t('agentOption.selectModel')
  for (const provider of modelProviders.value) {
    const model = provider.models.find(m => m.id === editedModel.value)
    if (model) return model.name
  }
  return t('agentOption.selectModel')
})

function toggleEditModelSelector() {
  showEditModelSelector.value = !showEditModelSelector.value
}

function selectEditModel(model_source: string, model: string) {
  editedModelSource.value = model_source
  editedModel.value = model
  showEditModelSelector.value = false
}

function handleEditModelClickOutside(event: Event) {
  if (editModelSelectorRef.value && !editModelSelectorRef.value.contains(event.target as Node)) {
    showEditModelSelector.value = false
  }
}

// 文件库相关方法
function triggerNewFileUpload() {
  newFileInput.value?.click()
}

function triggerEditFileUpload() {
  editFileInput.value?.click()
}

function handleNewFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (input?.files) {
    const newFiles = Array.from(input.files)
    newAgentFiles.value = [...newAgentFiles.value, ...newFiles]
    newFiles.forEach(file => {
      if (isImageFile(file)) {
        const key = getFileKey(file)
        if (!newFilePreviewUrls.value.has(key)) {
          newFilePreviewUrls.value.set(key, URL.createObjectURL(file))
        }
      }
    })
    input.value = ''
  }
}

function handleEditFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (input?.files) {
    const newFiles = Array.from(input.files)
    editedAgentNewFiles.value = [...editedAgentNewFiles.value, ...newFiles]
    newFiles.forEach(file => {
      if (isImageFile(file)) {
        const key = getFileKey(file)
        if (!editFilePreviewUrls.value.has(key)) {
          editFilePreviewUrls.value.set(key, URL.createObjectURL(file))
        }
      }
    })
    input.value = ''
  }
}

function removeNewFile(index: number) {
  const removed = newAgentFiles.value.splice(index, 1)[0]
  if (removed) revokeNewFilePreview(removed)
}

function removeEditNewFile(index: number) {
  const removed = editedAgentNewFiles.value.splice(index, 1)[0]
  if (removed) revokeEditFilePreview(removed)
}

function removeExistingFile(fileId: string) {
  agentFilesToDelete.value = [...agentFilesToDelete.value, fileId]
}

function getFileKey(file: File) {
  return `${file.name}_${file.size}_${file.lastModified}`
}

function getNewFileKey(file: File, idx: number) {
  return `new_${idx}_${getFileKey(file)}`
}

function getEditFileKey(file: File, idx: number) {
  return `edit_${idx}_${getFileKey(file)}`
}

function getFileExtension(file: File) {
  const name = file.name || ''
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

function getFileExtensionFromName(name: string) {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

function isImageFile(file: File) {
  const ext = getFileExtension(file)
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)
}

function getImagePreviewUrl(file: File, mode: 'new' | 'edit') {
  const urls = mode === 'new' ? newFilePreviewUrls : editFilePreviewUrls
  const key = getFileKey(file)
  const cached = urls.value.get(key)
  if (cached) return cached
  if (isImageFile(file)) {
    const url = URL.createObjectURL(file)
    urls.value.set(key, url)
    return url
  }
  return ''
}

function getFileIconUrl(file: File) {
  const ext = getFileExtension(file)
  if (['doc', 'docx'].includes(ext)) return DocIconUrl
  if (['xls', 'xlsx', 'csv'].includes(ext)) return ExcelIconUrl
  if (['ppt', 'pptx'].includes(ext)) return PptIconUrl
  if (['pdf'].includes(ext)) return PdfIconUrl
  return FileIconUrl
}

function getFileIconByExt(name: string) {
  const ext = getFileExtensionFromName(name)
  if (['doc', 'docx'].includes(ext)) return DocIconUrl
  if (['xls', 'xlsx', 'csv'].includes(ext)) return ExcelIconUrl
  if (['ppt', 'pptx'].includes(ext)) return PptIconUrl
  if (['pdf'].includes(ext)) return PdfIconUrl
  return FileIconUrl
}

function revokeNewFilePreview(file: File) {
  const key = getFileKey(file)
  const url = newFilePreviewUrls.value.get(key)
  if (url) {
    URL.revokeObjectURL(url)
    newFilePreviewUrls.value.delete(key)
  }
}

function revokeEditFilePreview(file: File) {
  const key = getFileKey(file)
  const url = editFilePreviewUrls.value.get(key)
  if (url) {
    URL.revokeObjectURL(url)
    editFilePreviewUrls.value.delete(key)
  }
}

function clearNewFilePreviews() {
  newFilePreviewUrls.value.forEach(url => URL.revokeObjectURL(url))
  newFilePreviewUrls.value.clear()
}

function clearEditFilePreviews() {
  editFilePreviewUrls.value.forEach(url => URL.revokeObjectURL(url))
  editFilePreviewUrls.value.clear()
}

// 文件内容预览（仅 readonly）
watch(selectedPreviewFile, () => {
  if (previewFileUrl.value) URL.revokeObjectURL(previewFileUrl.value)
  previewFileUrl.value = ''
  previewFileContent.value = ''
})

async function fetchAgentFileContent(filename: string) {
  const agent = displayAgent.value
  if (!agent) return
  selectedPreviewFile.value = filename
  try {
    const response = await axios.get(`/api/file_content/${filename}`, {
      params: { agent_id: agent.agent_id },
      responseType: 'blob'
    })
    const blob = response.data
    previewFileBlob.value = blob
    previewFileUrl.value = URL.createObjectURL(blob)
    previewError.value = ''

    if (isPreviewDocx.value) {
      const reader = new FileReader()
      reader.onload = async (e) => {
        const arrayBuffer = e.target?.result
        if (arrayBuffer instanceof ArrayBuffer) {
          try {
            const result = await mammoth.convertToHtml({ arrayBuffer })
            previewFileContent.value = result.value
          } catch {
            previewError.value = t('agentOption.cannotConvertDocx')
          }
        }
      }
      reader.readAsArrayBuffer(blob)
    } else if (isPreviewTextFile.value) {
      blob.text().then(text => {
        previewFileContent.value = text
      }).catch(() => {
        previewError.value = t('agentOption.cannotReadContent')
      })
    } else {
      previewFileContent.value = ''
    }
  } catch {
    previewError.value = t('agentOption.cannotPreviewType')
    previewFileUrl.value = ''
    previewFileContent.value = ''
  }
}

async function downloadAgentFile(filename: string) {
  const agent = displayAgent.value
  if (!agent) return
  try {
    const response = await axios.get(`/api/file_content/${filename}`, {
      params: { agent_id: agent.agent_id },
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err) {
    console.error('下载文件失败:', err)
  }
}

</script>

<style scoped>
/* Copy styles from KBOption.vue and replace kb with agent */
.agent-option-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.agent-option-container {
  background: #ffffff;
  border-radius: 20px;
  width: 90%;
  width: 120vh;
  height: 80vh;
  overflow: hidden;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.06),
    0 24px 60px -12px rgba(0, 0, 0, 0.18),
    0 12px 24px -8px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
}

/* ── Header (Apple-style light) ── */
.agent-option-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 26px 32px 20px;
  background: #ffffff;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.05);
  position: relative;
  z-index: 2;
}

.header-title-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.header-eyebrow {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #86868b;
  letter-spacing: 0.12em;
  line-height: 1;
  text-transform: uppercase;
}

.header-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-option-header h2 {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 1.5rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.022em;
  line-height: 1.18;
}

.header-hint {
  font-size: 0.75rem;
  font-weight: 400;
  color: #86868b;
  letter-spacing: -0.005em;
}

.close-btn {
  width: 30px;
  height: 30px;
  background: rgba(0, 0, 0, 0.04);
  border: none;
  cursor: pointer;
  color: #86868b;
  border-radius: 50%;
  display: grid;
  place-items: center;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
  flex-shrink: 0;
  margin-top: 4px;
  padding: 0;
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.08);
  color: #1d1d1f;
}

.close-btn:active {
  transform: scale(0.94);
}

.agent-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  background: #f5f5f7;
}

.agent-sidebar {
  width: 300px;
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
}

.agent-main {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
  background: #f5f5f7;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #86868b;
  font-size: 0.875rem;
  letter-spacing: -0.005em;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-block {
  margin-bottom: 14px;
}

.agent-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px 8px;
  background: transparent;
  border-radius: 0;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
  color: #6e6e73;
  font-size: 0.6875rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: opacity 0.18s ease;
}

.agent-block-header:hover {
  background: transparent;
  opacity: 0.7;
}

.agent-block-title {
  flex: 1;
}

.block-toggle-icon {
  flex-shrink: 0;
  color: #a1a1a6;
  transition: transform 0.2s;
}

.block-toggle-icon.expanded {
  transform: rotate(180deg);
}

.agent-block-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
  padding-left: 0;
}

.empty-block-hint {
  padding: 10px 14px;
  color: #a1a1a6;
  font-size: 0.8125rem;
  font-weight: 400;
  letter-spacing: -0.005em;
}

.agent-market-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  margin-bottom: 6px;
  padding: 9px 14px;
  background: #ffffff;
  color: #1d1d1f;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease, border-color 0.18s ease;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.agent-market-btn:hover {
  background: #fafafa;
  border-color: rgba(0, 0, 0, 0.12);
  color: #1d1d1f;
}

.agent-market-icon {
  opacity: 0.85;
}

.agent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.agent-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.agent-item.selected {
  background: #ffffff;
  border-color: rgba(0, 0, 0, 0.06);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.04),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.agent-name {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  line-height: 1.35;
}

.agent-type {
  display: inline-flex;
  align-items: center;
  padding: 6px 9px;
  border-radius: 30%;
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  background: #f4f6fb;
  border: 1px solid transparent;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.agent-type:hover {
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.single-type {
  color: #3f3f46;
  background: #f2f3f7;
  border-color: #d5d7de;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.multi-type {
  color: #9c3f02;
  background: #ffecc4;
  border-color: #f3c14a;
}

.agent-info {
  margin-bottom: 16px;
  padding: 4px 0 14px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.agent-info.is-editing {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 4px 0 14px;
  box-shadow: none;
}

.agent-info p {
  color: #6e6e73;
  margin: 8px 0;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
}

.agent-info-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  margin-bottom: 14px;
}

.agent-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 14px;
  border-radius: 980px;
  border: 1px solid transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  background: rgba(0, 0, 0, 0.05);
  color: #1d1d1f;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.2s ease;
}

.is-readonly .action-btn {
  border-color: transparent;
}

.action-btn:hover {
  background: rgba(0, 0, 0, 0.08);
}

.action-btn:active {
  transform: scale(0.97);
}

.action-btn.back-to-market {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.delete-doc {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  transition: opacity 0.2s;
  position: relative;
}

.delete-doc:hover {
  opacity: 0.7;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  text-align: center;
  color: #86868b;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid rgba(0, 0, 0, 0.06);
  border-top-color: #1d1d1f;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin-bottom: 12px;
}

.loading-spinner.small {
  width: 16px;
  height: 16px;
  border-width: 2px;
  margin-bottom: 0;
}

.loading-spinner.inline {
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.retry-btn {
  margin-top: 12px;
  padding: 7px 18px;
  background: #1d1d1f;
  color: #ffffff;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease, transform 0.2s ease;
}

.retry-btn:hover {
  background: #000;
}

.retry-btn:active {
  transform: scale(0.97);
}

.create-agent {
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent;
  margin-bottom: 14px;
}

.plus-box {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  background: #ffffff;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
  transition: background 0.18s ease, border-color 0.18s ease;
}

.plus-box:hover {
  background: #1d1d1f;
  border-color: #1d1d1f;
}

.plus-box:hover img {
  filter: brightness(0) invert(1);
}

.confirm-modal,
.error-modal {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 2000;
}

.confirm-content,
.error-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  width: 300px;
  text-align: center;
}

.confirm-buttons {
  display: flex;
  justify-content: space-around;
  margin-top: 20px;
}

.confirm-btn {
  background: #10b981;
  color: white;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.confirm-btn:hover {
  background: #059669;
}

.cancel-btn,
.ok-btn {
  background: #f3f4f6;
  color: #4b5563;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.cancel-btn:hover,
.ok-btn:hover {
  background: #e5e7eb;
}

/* 响应式 */
@media (max-width: 768px) {
  .agent-content {
    flex-direction: column;
  }
  
  .agent-sidebar {
    width: auto;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .agent-main {
    padding: 16px;
  }
}

@media (max-width: 640px) {
  .agent-option-container {
    width: 95%;
    max-height: 90vh;
  }
}

/* 发布状态样式：私有(更浅灰) / 已发布(绿) + 操作按钮 */
.publish-status-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: 8px;
}

.publish-status-label {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.publish-status-label.status-private {
  color: #b8bcc4;
  background: #fafafa;
  border: 1px solid #e8eaed;
}

.publish-status-label.status-published {
  color: #059669;
  background: #d1fae5;
}

.subscribe-btn {
  margin-left: 12px;
  padding: 6px 14px;
  font-size: 0.85rem;
  font-weight: 500;
  color: #fff;
  background: #3b82f6;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.subscribe-btn:hover:not(:disabled) {
  background: #2563eb;
}

.subscribe-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.subscribe-btn.unsubscribe {
  background: #64748b;
}

.subscribe-btn.unsubscribe:hover:not(:disabled) {
  background: #475569;
}

.publish-result-content p {
  margin: 0;
  font-size: 15px;
  color: #1f2937;
}

/* 智能体选项按钮和菜单（仿 conversation 样式） */
.agent-option-wrapper {
  position: relative;
}

.agent-option-btn {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 4px;
  opacity: 0.8;
  background: transparent;
  border: none;
  border-radius: 20%;
  cursor: pointer;
  transition: opacity 0.2s ease, background-color 0.2s ease;
}

.agent-option-btn:hover {
  opacity: 1;
  background-color: rgba(128, 128, 128, 0.226);
}

.agent-option-menu {
  position: fixed;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  padding: 8px;
  z-index: 3000;
  min-width: 140px;
}

.agent-option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 14px;
  color: #111827;
  transition: background-color 0.2s ease;
}

.agent-option-item:hover {
  background: #f3f4f6;
}

.agent-option-delete {
  color: #b91c1c;
}

.edit-input-agent {
  width: 97%;
  max-width: 100%;
  padding: 14px 16px;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.5;
  background: linear-gradient(180deg, #fafcfe 0%, #f3f5fa 100%);
  transition: border-color 0.2s, box-shadow 0.2s;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.04);
}

.edit-input-agent::placeholder {
  color: #9ca3af; /* Standard gray color to match typical textarea placeholder */
  font-family: inherit;
  font-size: 1rem;
  opacity: 1; /* Ensure full opacity */
  font-weight: 400;
}

.edit-input-agent:focus {
  outline: none;
  border-color: #d8dce6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
}
  
.edit-textarea {
  width: 97%;
  max-width: 100%;
  min-height: 80px;
  padding: 14px 16px;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  resize: vertical;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.5;
  background: linear-gradient(180deg, #fafcfe 0%, #f3f5fa 100%);
  transition: border-color 0.2s, box-shadow 0.2s;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.04);
}

.edit-textarea::placeholder {
  color: #9ca3af;
  font-family: inherit;
  font-size: 1rem;
  opacity: 1;
}

.edit-textarea:focus {
  outline: none;
  border-color: #d8dce6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
}

.save-edit {
  background: #10b981;
  color: white;
}

.save-edit:hover {
  background: #059669;
}

.cancel-edit {
  background: #f3f4f6;
  color: #4b5563;
}

.cancel-edit:hover {
  background: #e5e7eb;
}

.name-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-wrapper h3 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #2d333b;
}

.name-wrapper .edit-input-agent {
  flex: 1;
}

.agent-info-content {
  margin-top: 8px;
  padding-right: 16px;
}

.agent-info.is-readonly .agent-info-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-right: 0;
}

.field-group {
  margin-bottom: 24px;
}

.field-group label {
  display: block;
  font-weight: 500;
  margin-bottom: 4px;
  color: #2d333b;
}

.agent-info.is-readonly .field-group {
  margin: 0;
  padding: 14px 16px;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  background: linear-gradient(180deg, #fcfdfe 0%, #f8fafb 100%);
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.04);
}

.agent-info.is-editing .field-group {
  margin-bottom: 16px;
  padding: 12px 0;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.agent-info.is-editing .field-group label {
  font-weight: 500;
  color: #4b5563;
}

.agent-info.is-editing .edit-input-agent,
.agent-info.is-editing .edit-textarea,
.agent-info.is-editing .model-select-btn {
  background: #fdfefe;
  border: 1px solid #dce0e8;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.agent-info.is-editing .edit-input-agent:focus,
.agent-info.is-editing .edit-textarea:focus,
.agent-info.is-editing .model-select-btn:focus {
  border-color: #c5cad6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
}

.agent-info.is-readonly .field-group label {
  margin: 0 0 6px 0;
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.05em;
  color: #6b7280;
}

.agent-info.is-readonly .field-group p {
  margin: 0;
  color: #1f2937;
  font-weight: 400;
  line-height: 1.5;
  white-space: pre-line;
}

.agent-info.is-readonly .field-group p + p {
  color: #4b5563;
  font-weight: 400;
}

.agent-info.is-readonly .field-group .empty-state {
  grid-column: 1 / -1;
  margin: 0;
  border: none;
  padding: 0;
}

.inline-fields {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.inline-fields .field-group {
  flex: 1;
  min-width: 220px;
}

.field-group.compact {
  margin-bottom: 0;
}

.field-group.compact label {
  font-size: 12px;
  letter-spacing: 0.05em;
  color: #6b7280;
}

.field-group.compact p {
  margin: 0;
  font-weight: 400;
  color: #111827;
}

.pill-list {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.pill-item {
  width: 90%;
  padding: 8px 12px;
  background: #fdfeff;
  border: 1px solid #e2e5ec;
  border-radius: 10px;
  font-size: 0.95rem;
  color: #1f2937;
  font-weight: 400;
  line-height: 1.5;
  box-shadow: none;
  word-break: break-word;
}

.pill-title {
  display: block;
  color: #111827;
}

.pill-desc {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-text {
  margin: 0;
  color: #9ca3af;
}

.required {
  color: red;
  margin-left: 4px;
}

.list-selection {
  max-height: 440px;
  overflow-y: auto;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  padding: 10px 8px;
  background: linear-gradient(180deg, #fcfdfe 0%, #f8fafb 100%);
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.04);
}

.list-item {
  display: block;
  padding: 10px 12px;
  border: 1px solid #e6e8ee;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
}

.list-item-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.list-title {
  font-weight: 500;
  color: #1f2937;
}

.list-desc {
  display: block;
  margin-left: 26px;
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Add styles for toggle */
.toggle-wrapper {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin: 8px 0;
  gap: 20px;
}

.toggle-comment {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-left: 8px;
  flex-shrink: 0;
}

.toggle {
  width: 40px;
  height: 20px;
  background: #ccc;
  border-radius: 20px;
  position: relative;
  cursor: pointer;
  transition: background 0.3s;
}

.toggle.active {
  background: #10b981;
}

.toggle-circle {
  width: 18px;
  height: 18px;
  background: white;
  border-radius: 50%;
  position: absolute;
  top: 1px;
  left: 1px;
  transition: left 0.3s;
}

.toggle.active .toggle-circle {
  left: 21px;
}

.history-toggle {
  background-color: #f9fafb;
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  margin-top: 10px;
}

/* Model selector styles */
.model-selector {
  position: relative;
  width: 100%;
}

.model-select-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(180deg, #fafcfe 0%, #f3f5fa 100%);
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.04);
}

.model-select-btn:hover {
  border-color: #d8dce6;
}

.dropdown-icon {
  transition: transform 0.2s;
}

.dropdown-icon.rotate {
  transform: rotate(180deg);
}

.model-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  width: 100%;
  max-height: 300px;
  overflow-y: auto;
  background: white;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  z-index: 1000;
  margin-top: 4px;
}

.model-group {
  padding: 8px;
}

.model-group-title {
  font-weight: 600;
  padding: 8px 12px;
  color: #4b5563;
  border-bottom: 1px solid #e5e7eb;
}

.model-option {
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.model-option:hover {
  background: #f3f4f6;
}

.model-option.active {
  background: #108a162c;
  color: #1f3529;
  font-weight: 500;
}

/* 智能体表单：技能（系统 / 个人） */
.skill-agent-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.skill-agent-subsection {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fafbfc;
}

.skill-agent-subtitle {
  font-size: 0.85rem;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.skill-readonly-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-readonly-type-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 4px;
}

.skill-readonly-block .pill-list {
  margin-top: 0;
}

/* 工具分组样式 */
.tool-group {
  margin-bottom: 8px;
}

.tool-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  transition: background-color 0.2s ease, border-color 0.2s ease;
  margin-bottom: 4px;
}

.tool-group-header:hover {
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  border-color: #cbd5e1;
}

.tool-group-header-text {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.tool-group-name {
  font-weight: 600;
  color: #334155;
  font-size: 0.9rem;
}

.tool-group-count {
  background: #e2e8f0;
  color: #64748b;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}

.tool-group-selected {
  background: #d1fae5;
  color: #059669;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}

.tool-group-toggle {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #f1f5f9;
  color: #64748b;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.tool-group-header:hover .tool-group-toggle {
  background: #e2e8f0;
  color: #334155;
}

.tool-group-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 8px;
  border-left: 2px solid #f1f5f9;
  margin-left: 8px;
  margin-top: 4px;
}

.toggle-icon {
  transition: transform 0.2s ease;
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

/* 文件库样式 - 仿照 KBOption */
.file-library-row .file-library-wrapper {
  display: flex;
  gap: 0;
  overflow: hidden;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  background: linear-gradient(180deg, #fcfdfe 0%, #f8fafb 100%);
  /* 最大高度为宽度的 0.8 倍，aspect-ratio 5/4 即 height = 0.8 * width */
  width: 100%;
  max-height: 600px;
}

.file-library-wrapper:not(.file-library-edit) .agent-file-list {
  flex: 0 0 300px;
  height: 100%;
  min-height: 0;
  border-right: 1px solid #e6e9f0;
}

.file-library-wrapper.file-library-edit .agent-file-list {
  flex: 1;
  height: 100%;
  min-height: 0;
}

.agent-file-list {
  overflow-y: auto;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-sizing: border-box;
}

.upload-file-btn-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: transparent;
  border: 1px dashed #d1d5db;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  color: #6b7280;
  width: 100%;
  transition: all 0.2s;
}

.upload-file-btn-inline:hover {
  background: #f9fafb;
  border-color: #9ca3af;
  color: #374151;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #ffffff;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  transition: all 0.2s;
}

.file-item:hover {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.file-item.selected {
  background: #e5e7ee;
  border-color: #c5cad6;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: #1f2937;
}

.remove-file-btn-inline {
  flex-shrink: 0;
  padding: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-file-btn-inline:hover {
  opacity: 0.7;
}

.remove-file-btn-inline img {
  width: 16px;
  height: 16px;
}

.empty-docs {
  padding: 20px;
  text-align: center;
  color: #9ca3af;
  font-size: 14px;
}

/* 文件预览面板 */
.file-preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: #fafafa;
  overflow: hidden;
  min-width: 300px;
  min-height: 0;
}

.file-preview-panel .preview-header {
  position: sticky;
  top: 0;
  background: linear-gradient(to right, #f8f9fa, #e9ecef);
  padding: 10px 20px;
  border-bottom: 1px solid #dee2e6;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.file-preview-panel .preview-header h4 {
  margin: 0;
  font-size: 16px;
  color: #333;
}

.file-preview-panel .header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-preview-panel .icon-button {
  cursor: pointer;
  width: 20px;
  height: 20px;
}

.file-preview-panel .preview-content {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
  background-color: #ffffff;
  word-break: break-word;
}

.file-preview-panel .preview-image {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}

.file-preview-panel .html-iframe {
  width: 100%;
  min-height: 300px;
  border: none;
}

.file-preview-panel .error {
  color: #ef4444;
}
</style>
