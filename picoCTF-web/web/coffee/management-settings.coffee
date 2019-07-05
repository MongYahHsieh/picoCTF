Well = ReactBootstrap.Well
ButtonGroup = ReactBootstrap.ButtonGroup
Button = ReactBootstrap.Button
Grid = ReactBootstrap.Grid
Row = ReactBootstrap.Row
Col = ReactBootstrap.Col

update = React.addons.update

# The settings fields need to use the linked state mixin to avoid a lot of boilerplate.

GeneralTab = React.createClass
  propTypes:
    refresh: React.PropTypes.func.isRequired
    settings: React.PropTypes.object.isRequired

  getInitialState: ->
    @props.settings

  toggleFeedbackEnabled: ->
    @setState update @state,
      $set:
        enable_feedback: !@state.enable_feedback

  updateCompetitionName: (e) ->
    @setState update @state,
      $set:
        competition_name: e.target.value

  updateCompetitionURL: (e) ->
    @setState update @state,
      $set:
        competition_url: e.target.value

  updateStartTime: (value) ->
    @setState update @state,
      $set:
        start_time: value

  updateEndTime: (value) ->
    @setState update @state,
      $set:
        end_time: value

  updateMaxTeamSize: (e) ->
    @setState update @state,
      $set:
        max_team_size: parseInt(e.target.value)

  updateUsernameBlacklist: (e) ->
    @setState update @state,
      $set:
        username_blacklist: e.target.value.split('\n')

  pushUpdates: ->
    data = {
      enable_feedback: @state.enable_feedback
      competition_name: @state.competition_name
      competition_url: @state.competition_url
      start_time: new Date(@state.start_time).toISOString()
      end_time: new Date(@state.end_time).toISOString()
      max_team_size: @state.max_team_size
      username_blacklist: @state.username_blacklist
    }
    apiCall "PATCH", "/api/v1/settings", data
    .success ((data) ->
      apiNotify {"status": 1, "message": "Settings updated successfully"}
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  render: ->
    feedbackDescription = "Users will be able to review problems when this feature is enabled. The ratings will be available to you
      on the Problem tab."

    competitionNameDescription = "The name of the competition."
    competitionURLDescription = "The base URL for the competition website. This must be set in order for users to reset
      their passwords."

    startTimeDescription = "Before the competition has started, users will be able to register without viewing the problems."
    endTimeDescription = "After the competition has ended, users will no longer be able to submit keys to the challenges."

    maxTeamSizeDescription = "Maximum number of users that can join a single team."
    usernameBlacklistDescription = "Usernames that are unavailable for registration."

    <Well>
      <BooleanEntry name="Receive Problem Feedback" value={@state.enable_feedback} onChange=@toggleFeedbackEnabled description={feedbackDescription}/>
      <TextEntry name="Competition Name" value={@state.competition_name} type="text" onChange=@updateCompetitionName description={competitionNameDescription}/>
      <TextEntry name="Competition URL" value={@state.competition_url} type="text" onChange=@updateCompetitionURL description={competitionURLDescription}/>
      <TimeEntry name="Competition Start Time" value={@state.start_time} onChange=@updateStartTime description={startTimeDescription}/>
      <TimeEntry name="Competition End Time" value={@state.end_time} onChange=@updateEndTime description={endTimeDescription}/>
      <TextEntry name="Max Team Size" value={@state.max_team_size} type="number" onChange=@updateMaxTeamSize description={maxTeamSizeDescription} />
      <TextEntry name="Username Blacklist" value={@state.username_blacklist.join('\n')} type="textarea" onChange=@updateUsernameBlacklist description={usernameBlacklistDescription}/>
      <Row>
        <div className="text-center">
          <ButtonToolbar>
            <Button onClick={@pushUpdates}>Update</Button>
          </ButtonToolbar>
        </div>
      </Row>
    </Well>

EmailTab = React.createClass
  propTypes:
    refresh: React.PropTypes.func.isRequired
    emailSettings: React.PropTypes.object.isRequired
    emailFilterSettings: React.PropTypes.array.isRequired

  getInitialState: ->
    settings = @props.emailSettings
    settings.email_filter = @props.emailFilterSettings
    settings

  updateSMTPUrl: (e) ->
    @setState update @state,
      $set:
        smtp_url: e.target.value

  updateSMTPSecurity: (e) ->
    @setState update @state,
      $set: smtp_security: e.target.value

  updateSMTPPort: (e) ->
    @setState update @state,
      $set:
        smtp_port: parseInt(e.target.value)

  updateUsername: (e) ->
    @setState update @state,
      $set:
        email_username: e.target.value

  updatePassword: (e) ->
    @setState update @state,
      $set:
        email_password: e.target.value

  updateFromAddr: (e) ->
    @setState update @state,
      $set:
        from_addr: e.target.value

  updateFromName: (e) ->
    @setState update @state,
      $set:
        from_name: e.target.value

  updateMaxVerificationEmails: (e) ->
    @setState update @state,
      $set:
        max_verification_emails: parseInt(e.target.value)

  toggleEnabled: ->
    @setState update @state,
      $set:
        enable_email: !@state.enable_email

  toggleEmailVerification: ->
    @setState update @state,
      $set:
        email_verification: !@state.email_verification

  toggleSendParentVerificationEmail: ->
    @setState update @state,
      $set:
        parent_verification_email: !@state.parent_verification_email

  pushUpdates: (makeChange) ->
    pushData =
      email:
        enable_email: @state.enable_email
        email_verification: @state.email_verification
        max_verification_emails: @state.max_verification_emails
        parent_verification_email: @state.parent_verification_email
        smtp_url: @state.smtp_url
        smtp_port: @state.smtp_port
        email_username: @state.email_username
        email_password: @state.email_password
        from_addr: @state.from_addr
        from_name: @state.from_name
        smtp_security: @state.smtp_security
      email_filter: @state.email_filter

    if typeof(makeChange) == "function"
      pushData = makeChange pushData

    apiCall "PATCH", "/api/v1/settings", pushData
    .success ((data) ->
      apiNotify {"status": 1, "message": "Settings updated successfully"}
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  render: ->
    emailDescription = "Emails must be sent in order for users to reset their passwords."
    emailVerificationDescription = "Mandate email verification for new users"
    MaxVerificationEmailsDescription = "The number of times a verification email can be resent before the account is locked"
    parentEmailVerificationDescription = "Send an email to the parent's email address (if provided) upon registration"
    SMTPDescription = "The URL of the STMP server you are using"
    SMTPPortDescription = "The port of the running SMTP server"
    usernameDescription = "The username of the email account"
    passwordDescription = "The password of the email account"
    fromAddressDescription = "The address that the emails should be sent from"
    fromNameDescription = "The name to use for sending emails"
    SMTPSecurityDescription = "Security employed by the SMTP server"

    # This is pretty bad. Much of this file needs reworked.
    if @state.smtp_security == "TLS"
        securityOptions =
        <Input type="select" onChange={@updateSMTPSecurity} key="TLS">
          <option value="TLS">TLS</option>
          <option value="SSL">SSL</option>
        </Input>
    else
        securityOptions =
        <Input type="select" onChange={@updateSMTPSecurity} key="SSL">
          <option value="SSL">SSL</option>
          <option value="TLS">TLS</option>
        </Input>

    SMTPSecuritySelect =
    <Row>
      <Col md={4}>
        <h4 className="pull-left">
          <Hint text={SMTPSecurityDescription}/>
          Security
        </h4>
      </Col>
      <Col md={8}>
        {securityOptions}
      </Col>
    </Row>

    <Well>
      <Row>
        <Col xs={6}>
          <BooleanEntry name="Send Emails" value={@state.enable_email} onChange=@toggleEnabled description={emailDescription}/>
          <TextEntry name="SMTP URL" value={@state.smtp_url} type="text" onChange=@updateSMTPUrl description={SMTPDescription} />
          <TextEntry name="SMTP Port" value={@state.smtp_port} type="number" onChange=@updateSMTPPort description={SMTPPortDescription} />
          <TextEntry name="Email Username" value={@state.email_username} type="text" onChange=@updateUsername description={usernameDescription}/>
          <TextEntry name="Email Password" value={@state.email_password} type="password" onChange=@updatePassword description={passwordDescription}/>
          <TextEntry name="From Address" value={@state.from_addr} type="text" onChange=@updateFromAddr description={fromAddressDescription}/>
          <TextEntry name="From Name" value={@state.from_name} type="text" onChange=@updateFromName description={fromNameDescription}/>
          <BooleanEntry name="Email Verification" value={@state.email_verification} onChange=@toggleEmailVerification description={emailVerificationDescription}/>
          <TextEntry name="Max Verification Emails" value={@state.max_verification_emails} type="number" onChange=@updateMaxVerificationEmails description={MaxVerificationEmailsDescription} />
          <BooleanEntry name="Parent Verification Email" value={@state.parent_verification_email} onChange=@toggleSendParentVerificationEmail description={parentEmailVerificationDescription}/>
          {SMTPSecuritySelect}
          <Row>
            <div className="text-center">
              <ButtonToolbar>
                <Button onClick={@pushUpdates}>Update</Button>
              </ButtonToolbar>
            </div>
          </Row>
        </Col>
        <Col xs={6}>
          <EmailWhitelist pushUpdates={@pushUpdates} emails={@props.emailFilterSettings}/>
        </Col>
      </Row>
    </Well>

ShardingTab = React.createClass
  propTypes:
    refresh: React.PropTypes.func.isRequired
    shardingSettings: React.PropTypes.object.isRequired

  getInitialState: ->
    settings = @props.shardingSettings

  updateSteps: (e) ->
    @setState update @state,
      $set:
        steps: e.target.value.replace(/, +/g, ",").split(',').map(Number)

  updateDefaultStepping: (e) ->
    @setState update @state,
      $set:
        default_stepping: parseInt(e.target.value)

  toggleSharding: ->
    @setState update @state,
      $set:
        enable_sharding: !@state.enable_sharding

  toggleLimitRange: ->
    @setState update @state,
      $set:
        limit_added_range: !@state.limit_added_range

  pushUpdates: (makeChange) ->
    pushData =
      shell_servers:
        enable_sharding: @state.enable_sharding
        default_stepping: @state.default_stepping
        steps: @state.steps
        limit_added_range: @state.limit_added_range

    if typeof(makeChange) == "function"
      pushData = makeChange pushData

    apiCall "PATCH", "/api/v1/settings", pushData
    .success ((data) ->
      apiNotify {"status": 1, "message": "Settings updated successfully"}
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  assignServerNumbers: ->
    confirmDialog("This will assign server_numbers to all unassigned teams. This may include teams previously defaulted to server_number 1 and already given problem instances!", "Assign Server Numbers Confirmation", "Assign Server Numbers", "Cancel",
    () ->
      apiCall "POST", "/api/v1/shell_servers/update_assignments", {}
      .success (data) ->
        apiNotify {"status": 1, "message": "Server assignments updated"}
      .error (jqXHR) ->
        apiNotify {"status": 0, "message": jqXHR.responseJSON.message}
    , () ->
    )

  reassignServerNumbers: ->
    confirmDialog("This will reassign all teams. Problem instances will be randomized for any teams that change servers!", "Reassign Server Numbers Confirmation", "Reassign Server Numbers", "Cancel",
    () ->
      apiCall "POST", "/api/v1/shell_servers/update_assignments", {"include_assigned": true}
      .success (data) ->
        apiNotify {"status": 1, "message": "Server assigments updated"}
      .error (jqXHR) ->
        apiNotify {"status": 0, "message": jqXHR.responseJSON.message}
    , () ->
    )

  render: ->
    shardingDescription = "Sharding splits teams to different shell_servers based on stepping"
    defaultSteppingDescription = "Default stepping, applied after defined steps"
    stepsDescription = "Comma delimited list of stepping (e.g. '1000,1500,2000')"
    limitRangeDescription = "Limit assignments to the highest added server_number"

    <Well>
      <Row>
        <Col sm={8}>
          <BooleanEntry name="Enable Sharding" value={@state.enable_sharding} onChange=@toggleSharding description={shardingDescription}/>
          <TextEntry name="Defined Steps" value={@state.steps} type="text" onChange=@updateSteps description={stepsDescription}/>
          <TextEntry name="Default Stepping" value={@state.default_stepping} type="text" onChange=@updateDefaultStepping description={defaultSteppingDescription}/>
          <BooleanEntry name="Limit to Added Range" value={@state.limit_added_range} onChange=@toggleLimitRange description={limitRangeDescription}/>
          <br/><Button onClick={@assignServerNumbers}>Assign Server Numbers</Button> &nbsp; <Button onClick={@reassignServerNumbers}>Reassign All Server Numbers</Button><br/><br/>
          <Row>
            <div className="text-center">
              <ButtonToolbar>
                <Button onClick={@pushUpdates}>Update</Button>
              </ButtonToolbar>
            </div>
          </Row>
        </Col>
      </Row>
    </Well>

CaptchaTab = React.createClass
  propTypes:
    refresh: React.PropTypes.func.isRequired
    captchaSettings: React.PropTypes.object.isRequired

  getInitialState: ->
    settings = @props.captchaSettings

  toggleEnableCaptcha: ->
    @setState update @state,
      $set:
        enable_captcha: !@state.enable_captcha

  updateCaptchaURL: (e) ->
    @setState update @state,
      $set:
        captcha_url: e.target.value

  updateRecaptchaPublicKey: (e) ->
    @setState update @state,
      $set:
        reCAPTCHA_public_key: e.target.value

  updateRecaptchaPrivateKey: (e) ->
    @setState update @state,
      $set:
        reCAPTCHA_private_key: e.target.value

  pushUpdates: (makeChange) ->
    pushData =
      captcha:
        enable_captcha: @state.enable_captcha
        captcha_url: @state.captcha_url
        reCAPTCHA_public_key: @state.reCAPTCHA_public_key
        reCAPTCHA_private_key: @state.reCAPTCHA_private_key

    if typeof(makeChange) == "function"
      pushData = makeChange pushData

    apiCall "PATCH", "/api/v1/settings", pushData
    .success ((data) ->
      apiNotify {"status": 1, "message": "Settings updated successfully"}
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  render: ->
    enableCaptchaDescription = "Require users to solve a CAPTCHA when registering an account. Does not apply to invited or batch-registered accounts"
    captchaURLDescription = "URL to request a CAPTCHA"
    reCaptchaPublicKeyDescription = "Public key for the reCAPTCHA API"
    reCaptchaPrivateKeyDescription = "Private key for the reCAPTCHA API"

    <Well>
      <Row>
        <Col sm={8}>
          <BooleanEntry name="Enable CAPTCHA" value={@state.enable_captcha} onChange=@toggleEnableCaptcha description={enableCaptchaDescription}/>
          <TextEntry name="CAPTCHA URL" type="text" value={@state.captcha_url} onChange=@updateCaptchaURL description={captchaURLDescription}/>
          <TextEntry name="reCAPTCHA Public Key" type="textarea" value={@state.reCAPTCHA_public_key} onChange=@updateRecaptchaPublicKey description={reCaptchaPublicKeyDescription}/>
          <TextEntry name="reCAPTCHA Private Key" type="textarea" value={@state.reCAPTCHA_private_key} onChange=@updateRecaptchaPrivateKey description={reCaptchaPrivateKeyDescription}/>
          <Row>
            <div className="text-center">
              <ButtonToolbar>
                <Button onClick={@pushUpdates}>Update</Button>
              </ButtonToolbar>
            </div>
          </Row>
        </Col>
      </Row>
    </Well>

UserSearchTab = React.createClass
  getInitialState: ->
    search_field: "email"
    search_query: "email@example.com"

  updateSearchField: (value) ->
    @setState update @state,
      $set:
        search_field: value

  updateSearchQuery: (e) ->
    @setState update @state,
      $set:
        search_query: e.target.value

  pushUpdates: (makeChange) ->
    pushData = 
      field: @state.search_field
      query: @state.search_query

    if typeof(makeChange) == "function"
      pushData = makeChange pushData

    apiCall "POST", "/api/v1/users/search", pushData
    .success ((data) ->
      apiNotify {"status": 1, "message": "Search request processed"}
      alert JSON.stringify(data)
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  render: ->
    searchFieldDescription = "The field to be searched in the user database"
    searchQueryDescription = "The text of the query"

    <Well>
      <Row>
        <Col sm={8}>
          <OptionEntry name="Field" value={@state.search_field} options={["email", "parentemail"]} onChange=@updateSearchField description={searchFieldDescription}/>
          <TextEntry name="Query" type="text" value={@state.search_query} onChange=@updateSearchQuery description={searchQueryDescription}/>
          <Row>
            <div className="text-center">
              <ButtonToolbar>
                <Button onClick={@pushUpdates}>Search</Button>
              </ButtonToolbar>
            </div>
          </Row>
        </Col>
      </Row>
    </Well>

EligibilityTab = React.createClass
  propTypes:
    refresh: React.PropTypes.func.isRequired
    eligibilitySettings: React.PropTypes.object.isRequired

  getInitialState: ->
    settings = @props.eligibilitySettings

  updateCountry: (e) ->
    @setState update @state,
      $set:
        country: e.target.value

  pushUpdates: (makeChange) ->
    pushData =
      eligibility:
        country: @state.country

    if typeof(makeChange) == "function"
      pushData = makeChange pushData

    apiCall "PATCH", "/api/v1/settings", pushData
    .success ((data) ->
      apiNotify {"status": 1, "message": "Settings updated successfully"}
      @props.refresh()
    ).bind(this)
    .error (jqXHR) ->
      apiNotify {"status": 0, "message": jqXHR.responseJSON.message}

  render: ->
    countryDescription = "2-character code of the country considered eligible for this competition"

    <Well>
      <Row>
        <Col sm={8}>
          <TextEntry name="Country" type="text" value={@state.country} onChange=@updateCountry description={countryDescription}/>
          <Row>
            <div className="text-center">
              <ButtonToolbar>
                <Button onClick={@pushUpdates}>Update</Button>
              </ButtonToolbar>
            </div>
          </Row>
        </Col>
      </Row>
    </Well>

SettingsTab = React.createClass
  getInitialState: ->
    settings:
      start_time: "Tue, 21 May 2019 17:59:12 GMT"
      end_time: "Mon, 27 May 2019 17:59:12 GMT"
      competition_name: ""
      competition_url: ""
      enable_feedback: true
      max_team_size: 1
      username_blacklist: []
      email:
        email_verification: false
        parent_verification_email: false
        max_verification_emails: 3
        enable_email: false
        from_addr: ""
        smtp_url: ""
        smtp_port: 0
        email_username: ""
        email_password: ""
        from_name: ""
      email_filter: []
      shell_servers:
        enable_sharding: false
        default_stepping: 1
        steps: ""
        limit_added_range: false
      captcha:
        enable_captcha: false
        captcha_url: ""
        reCAPTCHA_public_key: ""
        reCAPTCHA_private_key: ""
      eligibility:
        usertype: "student"
        country: "US"

    tabKey: "general"

  onTabSelect: (tab) ->
    @setState update @state,
      tabKey:
        $set: tab

  refresh: ->
    apiCall "GET", "/api/v1/settings"
    .done ((data) ->
      @setState update @state,
        $set:
          settings: data
    ).bind this

  componentDidMount: ->
    @refresh()

  render: ->
    generalSettings =
      enable_feedback: @state.settings.enable_feedback
      competition_name: @state.settings.competition_name
      competition_url: @state.settings.competition_url
      start_time: @state.settings.start_time
      end_time: @state.settings.end_time
      max_team_size: @state.settings.max_team_size
      username_blacklist: @state.settings.username_blacklist
    <Well>
      <Grid>
        <Row>
          <h4> Configure the competition settings by choosing a tab below </h4>
        </Row>
        <TabbedArea activeKey={@state.tabKey} onSelect={@onTabSelect}>
          <TabPane eventKey='general' tab='General'>
            <GeneralTab refresh=@refresh settings={generalSettings} key={Math.random()}/>
          </TabPane>

          <TabPane eventKey='sharding' tab='Sharding'>
            <ShardingTab refresh={@refresh} shardingSettings={@state.settings.shell_servers} key={Math.random()}/>
          </TabPane>

          <TabPane eventKey='email' tab='Email'>
            <EmailTab refresh={@refresh} emailSettings={@state.settings.email} emailFilterSettings={@state.settings.email_filter} key={Math.random()}/>
          </TabPane>

          <TabPane eventKey='captcha' tab='CAPTCHA'>
            <CaptchaTab refresh={@refresh} captchaSettings={@state.settings.captcha} key={Math.random()}/>
          </TabPane>

          <TabPane eventKey='eligibility' tab='Eligibility'>
            <EligibilityTab refresh={@refresh} eligibilitySettings={@state.settings.eligibility} key={Math.random()}/>
          </TabPane>

          <TabPane eventKey='userSearch' tab='User Search'>
            <UserSearchTab refresh={@refresh} key={Math.random()}/>
          </TabPane>
        </TabbedArea>
      </Grid>
    </Well>
