const updatePassword = function(e) {
  e.preventDefault();
  const data = {
    current_password: $("#current-password").val(),
    new_password: $("#new-password").val(),
    new_password_confirmation: $("#new-password-confirmation").val()
  };
  apiCall(
    "POST",
    "/api/v1/user/update_password",
    data,
    "Authentication",
    "UpdatePassword"
  )
    .done(data =>
      apiNotify(
        { status: 1, message: "Your password has been successfully updated!" },
        "/account"
      )
    )
    .fail(jqXHR =>
      apiNotify({ status: 0, message: jqXHR.responseJSON.message })
    );
};

const resetPassword = function(e) {
  e.preventDefault();
  const data = {
    reset_token: window.location.hash.substring(1),
    new_password: $("#password-reset-form input[name=new-password]").val(),
    new_password_confirmation: $(
      "#password-reset-form input[name=new-password-confirmation]"
    ).val()
  };
  apiCall(
    "POST",
    "/api/v1/user/reset_password",
    data,
    "Authentication",
    "ResetPassword"
  )
    .done(function(data) {
      ga("send", "event", "Authentication", "ResetPassword", "Success");
      apiNotify(
        { status: 1, message: "Your password has been reset" },
        "/"
      );
    })
    .fail(jqXHR =>
      apiNotify({ status: 0, message: jqXHR.responseJSON.message })
    );
};

const disableAccount = function(e) {
  e.preventDefault();
  confirmDialog(
    "This will delete your account, drop you from your team, and prevent you from playing!",
    "Delete Account Confirmation",
    "Delete Account",
    "Cancel",
    function() {
      const data = {
        password: $("#disable-account-form input[name=current-password]").val()
      };
      apiCall(
        "POST",
        "/api/v1/user/disable_account",
        data,
        "Authentication",
        "DisableAccount"
      )
        .done(data =>
          apiNotify(
            { status: 1, message: "Your account has been deleted." },
            "/"
          )
        )
        .fail(jqXHR =>
          apiNotify({ status: 0, message: jqXHR.responseJSON.message })
        );
    }
  );
};

const downloadData = function(e) {
  e.preventDefault();
  apiCall("GET", "/api/v1/user/export")
    .done(data =>
      download(
        JSON.stringify(data, null, 2),
        "Account Data.txt",
        "application/json"
      )
    )
    .fail(jqXHR =>
      apiNotify({ status: 0, message: jqXHR.responseJSON.message })
    );
};

const { Input } = ReactBootstrap;
const { Row } = ReactBootstrap;
const { Col } = ReactBootstrap;
const { Button } = ReactBootstrap;
const { Panel } = ReactBootstrap;
const { Glyphicon } = ReactBootstrap;
const { ButtonInput } = ReactBootstrap;
const { ButtonGroup } = ReactBootstrap;

const { update } = React.addons;

// Should figure out how we want to share components.
const TeamManagementForm = React.createClass({
  mixins: [React.addons.LinkedStateMixin],

  getInitialState() {
    return {
      user: {},
      team: {},
      team_name: "",
      team_password: ""
    };
  },

  componentWillMount() {
    addAjaxListener("teamManagementFormState", "/api/v1/user", data => {
      this.setState(update(this.state, { user: { $set: data } }));
    });

    apiCall("GET", "/api/v1/team").done(data => {
      this.setState(update(this.state, { team: { $set: data } }));
    });
  },

  onTeamRegistration(e) {
    e.preventDefault();
    if (!this.state.team_name || !this.state.team_password) {
      apiNotify({
        status: 0,
        message: "Invalid team name or password."
      });
    } else {
      const data = {
        team_name: this.state.team_name,
        team_password: this.state.team_password
      };
      apiCall("POST", "/api/v1/teams", data)
        .done(data => (document.location.href = "/profile"))
        .fail(jqXHR =>
          apiNotify({ status: 0, message: jqXHR.responseJSON.message })
        );
    }
  },

  onTeamJoin(e) {
    e.preventDefault();
    const data = {
      team_name: this.state.team_name,
      team_password: this.state.team_password
    };
    apiCall("POST", "/api/v1/team/join", data)
      .done(data => (document.location.href = "/profile"))
      .fail(jqXHR =>
        apiNotify({ status: 0, message: jqXHR.responseJSON.message })
      );
  },

  onTeamPasswordChange(e) {
    e.preventDefault();
    if (this.state.team_password !== this.state.confirm_team_password) {
      apiNotify({ status: 0, message: "Passwords do not match." });
    } else {
      const newpass = this.state.team_password;
      const newpass_confirm = this.state.confirm_team_password;
      confirmDialog(
        "This will change the password needed to join your team.",
        "Team Password Change Confirmation",
        "Confirm",
        "Cancel",
        function() {
          const data = {
            new_password: newpass,
            new_password_confirmation: newpass_confirm
          };
          apiCall("POST", "/api/v1/team/update_password", data)
            .done(data =>
              apiNotify(
                {
                  status: 1,
                  message: "Your team password has been successfully updated!"
                },
                "/account"
              )
            )
            .fail(jqXHR =>
              apiNotify({ status: 0, message: jqXHR.responseJSON.message })
            );
        }
      );
    }
  },

  listMembers() {
    return this.state.team["members"].map((member, i) => (
      <li key={i}>
        {member.username} (
        <span className="capitalize">
          {member.usertype} - {member.country}
        </span>
        )
      </li>
    ));
  },

  render() {
    if (this.state.team.max_team_size > 1 && !this.state.user.teacher) {
      window.$("#team-management-container").show();
      const towerGlyph = <Glyphicon glyph="tower" />;
      const lockGlyph = <Glyphicon glyph="lock" />;

      const teamCreated =
        this.state.user &&
        this.state.user.username !== this.state.team.team_name;
      if (teamCreated) {
        return (
          <Panel header="Team Management">
            <p>
              <strong>Team Name:</strong> {this.state.team.team_name}
            </p>
            <p>
              <strong>Members</strong> ({this.state.team.members.length}/
              {this.state.team.max_team_size}):
            </p>
            <ul>{this.listMembers()}</ul>
            <hr />
            <form onSubmit={this.onTeamPasswordChange}>
              <Input
                type="password"
                valueLink={this.linkState("team_password")}
                addonBefore={lockGlyph}
                label="New Team Password"
                required={true}
              />
              <Input
                type="password"
                valueLink={this.linkState("confirm_team_password")}
                addonBefore={lockGlyph}
                label="Confirm New Team Password"
                required={true}
              />
              <Col md={6}>
                <Button type="submit">Change Team Password</Button>
              </Col>
            </form>
          </Panel>
        );
      } else {
        return (
          <Panel header="Team Management">
            <p>{`Your team name may be visible to other users. Do not include your real name or any other personal information.
Also, to avoid confusion on the scoreboard, you may not create a team that shares the same name as an existing user.`}</p>
            <form onSubmit={this.onTeamJoin}>
              <Input
                type="text"
                valueLink={this.linkState("team_name")}
                addonBefore={towerGlyph}
                label="Team Name"
                required={true}
              />
              <Input
                type="password"
                valueLink={this.linkState("team_password")}
                addonBefore={lockGlyph}
                label="Team Password"
                required={true}
              />
              <Col md={6}>
                <span>
                  <Button type="submit">Join Team</Button>
                  <Button onClick={this.onTeamRegistration}>
                    Register Team
                  </Button>
                </span>
              </Col>
            </form>
          </Panel>
        );
      }
    } else {
      return <div />;
    }
  }
});

$(function() {
  $("#password-update-form").on("submit", updatePassword);
  $("#password-reset-form").on("submit", resetPassword);
  $("#disable-account-form").on("submit", disableAccount);
  $("#download-data-form").on("submit", downloadData);

  ReactDOM.render(
    <TeamManagementForm />,
    document.getElementById("team-management")
  );
});
